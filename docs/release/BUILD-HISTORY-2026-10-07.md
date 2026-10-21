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

## Authorized AI call evidence API — October 15, 2026

- Added GET /ai/model-logs with newest-first cursor pagination, optional counts and typed
  configuration/hash/token/outcome/actor evidence. No provider call or proposal content read.
- Workspace-wide settings.manage sees tenant calls; ai.use sees only its own actor id and kind.
  These predicates apply before counts and pagination. A scoped administrator is refused unless
  also holding ai.use, which still returns only that actor's calls. Unsupported filters refuse.
- Two PostgreSQL API tests and eight route architecture checks pass. Backend typing (795 files),
  frontend typing, generated OpenAPI/types and full lint pass. The full frozen CI remains active
  on 3cf8f5b and is not evidence for this change. See docs/release/CI-2026-10-15.md.
- Call-log UI/drawer/export, standard J-19 and remaining release/accounting gates stay open.
  No deployment or provider call. Published directly to main after verification.

## AI call-log screen and bookmarked evidence — October 15, 2026

- Added /settings/ai/call-log with the shared grid, newest-first 50-row API pages, outcomes,
  token counters, latency and actor/configuration evidence. Named-entity settings grants do not
  open workspace evidence; ai.use opens only the actor's own list through the server's rules.
- A docked drawer reads GET /ai/model-logs/{id}; bookmarks/reloads reauthorize the call instead
  of trusting a retained row. Backend tests prove owner and tenant detail refusal as 404.
- Full frontend suite: 2,164 tests pass in 203 files. Ten API/route checks, 35 focused frontend
  checks, backend typing (795 files), frontend typing and full lint pass. Real Chromium with API/PostgreSQL passes grid, drawer and bookmark reload;
  screenshots inspected and the drawer layout corrected. Details: docs/release/CI-2026-10-15.md.
- CSV/XLSX export, saved views, linked proposals and hash-copy controls remain open, as do J-19,
  broader release gates and independent accounting sign-off. No deployment or provider calls.

## Preserve unknown token usage in call evidence — October 15, 2026

- Added usage_known to call-log list/detail, using the exact SQL evidence predicate used by
  budget admission. The screen shows Unknown and a drawer explanation for missing usage;
  reported zero remains zero. Compatibility counters and retained records are not rewritten.
- Twenty-four API/PostgreSQL budget checks and six screen checks pass. Backend typing (796
  files), frontend typing and full lint pass. The prior full frontend result is not relabelled as covering
  this correction. Evidence is recorded in docs/release/CI-2026-10-15.md.
- Usage reconciliation, remaining call-log features and broader release/accounting gates are
  still open. No deployment or provider calls; publish directly to main after verification.

## Saved call-log layouts — October 15, 2026

- Connected SF-15:ai-call-log to the shared saved-view selector and controlled grid columns.
  Private layouts persist under the current membership; shared layouts restore presentation
  without changing call visibility. Call records and drawer ids are never saved in view config.
- Opening a call now retains the active view and sort. Twenty-one screen/selector/settings
  checks, frontend typing and full lint pass; evidence is in docs/release/CI-2026-10-15.md.
- Export, linked proposals, hash-copy controls, J-19 and broader release/accounting gates stay
  open. No deployment or provider calls. Publish directly to main after verification.

## Authorized AI export dataset foundation — October 15, 2026

- Added the internal call-export dataset using current owner/tenant visibility and standard
  CSV/XLSX writers. Unknown usage stays distinct from zero; totals name only known usage.
- Real PostgreSQL plus parsed CSV/XLSX witnesses prove scope, spreadsheet-formula escaping and
  unknown/zero cells. An initial test caught unrestricted system identity access; the builder
  now requires a user/API-client identity and refuses system/operator/missing-ID contexts.
- Six API/export/formula checks, the final identity check, backend typing (796 files) and full
  lint pass. Evidence: docs/release/CI-2026-10-15.md.
- Export is NOT yet public: next wire queued execution/current-grant reconstruction, retained
  output ownership/revocation checks and the download menu. No deployment/provider calls.
  Other call-log and broader release/accounting gates remain open.

## Bound AI export authorization — October 15, 2026

- Added a frozen/versioned server-captured export binding: original tenant, actor id/kind and
  maximum OWN/TENANT scope. Dataset builds require it; subsequent promotion cannot widen an
  own-call request, and a workspace export still requires current workspace-wide settings.manage.
- PostgreSQL/CSV/XLSX verification covers serialized bindings, promotion/demotion, cross-owner,
  cross-tenant, actor-kind and permission/scope loss. Three API checks and backend typing (796
  files) and full lint also pass. Evidence: docs/release/CI-2026-10-15.md.
- Queued export is still unfinished. Next persist the binding, reconstruct current grants in
  the worker, guard replay/download before returning any bytes, and wire the menu. Other release
  gates remain open. No deployment/provider calls; publish directly to main after verification.

## Current requester grants for export workers — October 15, 2026

- Extracted persisted-job requester reconstruction for AI_TASK and REPORT_RUN: active human,
  current grants and live matching attempt required; no reconstructed login/MFA session.
  AI jobs still narrow entity access to ai.use before reading sources.
- Export capture/build guards now require report.export; TENANT requires its workspace-wide
  scope. Source visibility remains required. Thirteen focused tests, backend typing (797 files)
  and full lint pass; evidence: docs/release/CI-2026-10-15.md.
- These are prerequisites, not a completed queued export. Persisted bindings, worker integration,
  every output/replay read and the download menu remain open. No deployment/provider calls.

## Retained export ownership across report and job reads — October 15, 2026

- Migration 0157 adds an immutable, validated requester binding to report_run. It refuses
  malformed/cross-owner bindings and downgrade while bindings survive. A partial tenant/job
  index supports job visibility checks.
- Shared report and job read predicates now require the original actor and current source/
  export grants for bound exports, including for audit readers. Existing unbound reports keep
  their rules. Submission, worker capture/build and UI integration remain unfinished.
- Verification evidence and the migration round trip are recorded in docs/release/CI-2026-10-15.md.
  No deployment, provider calls or accounting sign-off; production readiness remains unproven.

## Queued call-export execution and revocation — October 15, 2026

- Internal run creation captures the requester binding; reruns preserve its maximum scope.
  REPORT_RUN reloads the human's current grants before start, completed replay, build and output
  storage. Dataset reads use that human context, not SYSTEM. API-client execution refuses.
- Call exports omit ledger-head metadata and declare live/open source capture. Real queued
  CSV/XLSX tests cover promotion, retained OWN scope, replay and permission loss before execution
  and during rendering. Public catalogue/API activation and the download UI remain unfinished.
- Report unit verification passes 941 checks; detailed worker, typing and lint evidence is in
  docs/release/CI-2026-10-15.md. No deployment/provider calls/sign-off; broader gates remain open.

## Call-export API authorization and cached replies — October 15, 2026

- Source-only AI users/settings administrators can use this export with report.export; these
  grants do not admit accounting reports. Source MFA and requester binding guard reads.
- Per-subject commands can guard the actual cached reply after lookup. Export replay checks its
  retained scope and refreshes session/grants after that potentially waiting lookup. OWN stays
  OWN after promotion; a retained TENANT reply refuses demotion. No duplicate route guards.
- Public catalogue registration and the download UI remain pending. Verification details are in
  docs/release/CI-2026-10-15.md. No deployment/provider calls/sign-off; broader gates remain open.

## Public call-export catalogue — October 15, 2026

- Migration 0158 registers ai_call_log_export for CSV/XLSX through the existing report API.
  Its closed, empty parameter schema refuses misleading entity/history/owner filters; the
  requester binding supplies scope, and reruns evaluate the current authorized population.
- Worker tests now use the actual migration seed instead of temporary registration. Catalogue
  metadata, specification inventories and default-role visibility expectations include the code.
- Definition removal must refuse while retained runs reference it. Migration/worker verification
  is recorded in docs/release/CI-2026-10-15.md. The call-log download menu remains pending.
- No deployment or live provider calls. Overall release gates and accounting sign-off remain open.

## Call-log CSV/XLSX download controls — October 15, 2026

- The call-log toolbar creates requester-bound exports, polls their jobs, reads completed runs
  and saves authorized output bytes. It explains that hidden grid columns are included.
- Export requires the matching source/export scopes; source-only users stay on the call-log
  screen. Duplicate submissions are disabled, failures are shown, and leaving the screen
  suppresses late downloads. The command helper exposes job polling errors to this flow.
- Frontend and real local Chromium/API/worker verification is recorded in
  docs/release/CI-2026-10-15.md. No deployment or live provider calls; overall release gates,
  remaining call-log navigation/copy controls and independent accounting sign-off remain open.

## Call-log proposal links and hash copying — October 15, 2026

- Proposal lists accept ai_model_log_id while preserving source authorization, counts and
  cursor binding. The call drawer shows authorized links, without rendering proposal content.
- Extraction links open contract review; number explanations open their bound trace with a
  freshly authorized retained narrative and same-trace citation links. Cached content stays
  hidden during reauthorization and on refusal or a source mismatch.
- Hash buttons copy complete retained hashes, hide absent response hashes and report clipboard
  refusal. Verification is recorded in docs/release/CI-2026-10-15.md.
- No deployment or live provider calls. Explain submission, other planned AI operations,
  standard demo/J-19, broader release gates and independent accounting sign-off remain open.

## Contract exception counts and filtering — October 15, 2026

- Replaced the hard-coded zero in contract headers/list rows with current related open-item
  counts. Has exceptions now supports both true and false before pagination and totals.
- Attribution includes explicit contracts, obligation owners, current group members and
  combination-suggestion payloads. Explicit contract attribution does not spread to the group;
  repeated occurrences count once. Tenant/entity RLS remains in force.
- Integration, scope and contract API regression evidence is recorded in
  docs/release/CI-2026-10-15.md. Modified-in-period and recent-view quick lists remain open.
- No deployment or accounting-policy change; full release gates and independent sign-off remain.

## Applied-modification contract filters — October 15, 2026

- Modified-in-period and Modified this period now read APPLIED modification effective dates
  within the contracting entity's fiscal calendar. The quick list follows as_of, falling back
  to entity-local today. EXISTS avoids duplicate contracts and filters before page/count logic.
- Verification is recorded in docs/release/CI-2026-10-15.md. Recently viewed remains open;
  this does not reconstruct historical modification status or change accounting calculations.
- No deployment; broader release verification and independent accounting sign-off remain open.

## Private recently viewed contracts — October 15, 2026

- Revision 0159 stores the last 50 successful contract opens per caller, with tenant and owner
  RLS and serialized updates/pruning. Failed reads and lists never record visits.
- Recently viewed uses that history, rechecks current contract scope and supports ordinary
  filters, counts and pagination. Reopening a contract moves it to the front.
- Verification is recorded in docs/release/CI-2026-10-15.md. No accounting events or contract
  versions are changed. No deployment; full release gates and independent sign-off remain open.

## Privacy catalogue coverage gate — October 15, 2026

- Classified the new private navigation history and the retained AI file references/export
  authorization binding using existing catalogue rules. Corrected its documentation header and
  kept the file-hold test's complete list of retained AI sources.
- Added make privacy-check to lint: 90 source-only checks cover catalogue/doc agreement,
  shredding rules, anonymisation names, patterns and offsets. This executes assertions rather
  than relying on collection. Verification is in docs/release/CI-2026-10-15.md.
- No deployment or accounting-policy change. Broader release checks and sign-off remain open.

## Manual acceptance and side-letter terms — October 15, 2026

- Manual create/edit forms now state acceptance clauses and side letters as Yes, No or Not
  stated. New drafts leave both unknown; edits preserve saved answers and can clear them.
- This fixes draft edits silently dropping existing terms. Activation controls remain unchanged;
  omitted import terms remain unknown; see LIMITS-1.0.md. Verification is in CI-2026-10-15.md.
- No deployment or accounting-policy change; broader release gates and sign-off remain open.

## CSV acceptance and side-letter evidence — October 15, 2026

- CSV v2 already supports these terms. New PostgreSQL regressions verify approved booking and
  replacement preserve true/false/null in events and projections, and reject contradictory rows.
- Three tests and backend typing pass; evidence is in docs/release/CI-2026-10-15.md.
  Omitted terms remain unknown. No production behavior, activation policy or deployment change.

## SSP override entity context — October 15, 2026

- New override previews retain the contract and source-book entities, all-entity scope and
  mismatch indicator; the approval table names them explicitly. Older previews stay unchanged.
- Source-book access and approved-book scope protections remain in force. Cross-entity pricing
  policy and additional-review requirements remain open; this change makes the facts visible.
- Verification is recorded in docs/release/CI-2026-10-15.md. No deployment.

## Runtime audit and local container verification — October 15, 2026

- make audit-deps passed on clean 74bd148: all 86 pinned Python runtime packages audited,
  with zero Python vulnerabilities and zero npm runtime advisories. Source binding is verified.
- Local Compose verification also passed on 74bd148: migrations, readiness, CSP and worker
  health, followed by verified cleanup. The earlier host-mount stall did not recur.
- Evidence is in docs/release/CI-2026-10-15.md. Final-candidate checks remain required.

## Security scan report validation — October 15, 2026

- Fixed a demonstrated false pass for empty ZAP reports. The gate now requires the target site,
  explicit alert arrays and known risk codes. Valid zero-alert reports remain accepted.
- Script regressions, typing and lint pass; evidence is in docs/release/CI-2026-10-15.md.
  Live verification passed on 4c4b583. No deployment or alert suppression.

## Worker container health probe — October 15, 2026

- A live baseline run exposed five-second probe timeouts despite a fresh heartbeat. The image
  now calls a small module using the existing freshness function, without importing worker
  handlers or the CLI. The 60-second freshness rule and Docker timeout remain unchanged.
- Unit/process and Linux-container checks pass. The committed 4c4b583 baseline passes too;
  the real Docker health command completed in about 0.92 seconds.
  Evidence is in docs/release/CI-2026-10-15.md. No deployment.

## Current report availability — October 15, 2026

- Reconciled LIMITS B4-6/C-11 against the runtime registry: 40 builders among 57 definitions,
  with 17 generic builders still absent. First-close evidence packs use their separate API.
- Labelled the old fifteen-test failure list as historical; registration is not accounting
  acceptance. Four catalogue checks pass; details are in docs/release/CI-2026-10-15.md.
- The isolated all-workspace recovery drill passed on frozen d7e8715: eight tenants, 306 files,
  702 tables, no missing or reduced table counts, and verified cleanup. No deployment.

## Re-lock snapshot integrity — October 15, 2026

- Re-lock comparisons now verify the stored hash and row count of both the previous and newly
  frozen datasets before comparing them. A mismatch refuses the comparison; no live fallback.
- Focused corruption and comparison tests and backend typing pass. The database re-lock workflow and lint
  pass; evidence is recorded in docs/release/CI-2026-10-15.md.
- RPT-38 driver attribution and the pre-approval diff remain outstanding.

## Close comparison navigation — October 15, 2026

- The history grid, drawer and keyboard action now traverse reopen records to the prior
  freezing lock before constructing RPT-38 selectors. Incomplete, cyclic or out-of-order
  history produces no comparison link; permanent-lock records are not report snapshots.
- Correcting the synthetic history to the real backend chain reproduced two link failures.
  All 16 history tests, frontend typing and repository lint pass.
- The missing RPT-38 builder and driver attribution remain open. This repairs its entry path.

## Typed computation evidence — October 15, 2026

- Revision 0160 retains encrypted typed inputs and canonical outputs for new computations,
  with original file digests, logical hashes, book coverage, predecessor and ledger cutoffs
  captured before their own postings. Storage failure rolls back the computation.
- Existing computations are not reconstructed or backfilled. Evidence has no generic download
  route and remains held against deletion. Verified backfill and replay jobs remain open.
- Fourteen database regressions pass, including the close/reopen/re-lock workflow. Schema,
  privacy, typing and lint verification is recorded in docs/release/CI-2026-10-15.md.
- This supplies new source evidence needed by RPT-38; its replay integration and report remain open.

## Verified computation sources for report replay — October 15, 2026

- The internal reader checks report.run over the complete stored group and performing entities
  before opening files, then validates raw/logical hashes, codec/cutoff, group membership,
  output book coverage, predecessor heads and ledger-cutoff shape. SYSTEM has no implicit grant.
- Old inputs remain stable after the group advances. Missing evidence never rebuilds from current
  state. Corruption and scope checks pass; final verification is in CI-2026-10-15.md.
- This reader is not yet wired to RPT-38. Replay orchestration, ledger cross-checks and persisted
  replay verification remain outstanding. Local recovery on frozen 659314a passed.

## Malformed replay evidence — October 15, 2026

- Malformed input/output evidence now produces an integrity mismatch before engine execution,
  including missing input bodies, invalid decimal tags, invalid JSON/UTF-8 and non-object outputs.
  The shared codec also rejects non-finite decimals. No current-state fallback is introduced.
- Ten failure-first regressions reproduced uncaught parsing exceptions. Replay/codec checks and
  final typing/lint evidence are recorded in docs/release/CI-2026-10-15.md.
- Persisted replay verification, release orchestration and RPT-38 remain outstanding.

## Replay job execution identity — October 15, 2026

- Handlers can read the registry's exact task_id and attempt number through read-only context
  properties. Inline work has neither, including when it inherits a guarded parent runtime.
- Database coverage checks retry identity, stale-task fencing and duplicate delivery. The
  transaction inventory now names the existing SCH-11 tenant-directory read; writes stay guarded.
- Persistence tables, verification handler and same-group scheduler locking remain outstanding.
  Verification evidence is recorded in docs/release/CI-2026-10-15.md.

## Durable scheduler execution locks — October 15, 2026

- Job creation accepts an execution lock retained in immutable, reserved metadata. Every
  dispatch reloads it, including retries and stranded-task recovery; handlers do not receive it.
  A dispatch cannot replace the stored lock. Per-job waiting deduplication remains separate.
- Database verification exercises the actual scheduler fetch function for same-group exclusion
  and independent-group progress. Final results are recorded in docs/release/CI-2026-10-15.md.
- Replay fan-out must supply verify:<group id>; persisted verification and its transactional
  advisory lock remain outstanding. No replay handler is newly registered by this change.

## Verification write transaction safeguards — October 15, 2026

- Recording an ERROR preserves the group's nonterminal state so aggregation waits for retry
  or exhaustion. Only an accepted non-error result marks the group COMPLETE.
- A PostgreSQL adapter now implements the execution-lock port in the writer's existing
  transaction. The lock lasts through commit/rollback, beyond the Python acquire block.
- Verification results are recorded in docs/release/CI-2026-10-15.md. The database store and
  replay handler remain outstanding; the adapter is not yet wired to a production write path.

## Release verification schema — October 15, 2026

- Revision 0161 adds per-release validation, frozen attempts/group selections and immutable
  verification results. Tenant RLS, execution identity, task deduplication, set-once acceptance,
  same-selection guards and retained file holds are enforced by the schema.
- Existing privacy/snapshot inventories now classify these four tables; synthetic parser controls
  preserve coverage of their former prose/hybrid declarations. Populated downgrade is refused.
- Verification evidence is in docs/release/CI-2026-10-15.md. Fan-out/handler,
  validation dataset publication and release admission remain unfinished; schema is not enablement.

## Verification result persistence — October 15, 2026

- The runtime store binds each decision to the actual scheduler task, process release and
  frozen group/source selection. Result, accepted pointer, state and contract audit event
  commit together; duplicate delivery writes no duplicate evidence. ERROR remains retryable.
- Targeted verification is recorded in docs/release/CI-2026-10-15.md. Handler/fan-out,
  dataset publication, selection creation and release admission remain unfinished.
- The older full CI on frozen 3cf8f5b ended with 11,567 passed and 22 failed. Its failures
  require current-main triage; it is not current-candidate acceptance.

## Frozen-CI failure triage — October 15, 2026

- Rechecked the old failure nodes against current main: report-source scope inventory and
  estimate-upload permission assertions needed updates. Upload-for-AI does not grant estimate
  attachment rights. The settings fixture now uses independent administrator author/approver.
- Job heartbeat verification now includes AI and release-verification foreign keys. Expanded
  job/settings database checks pass; exact evidence is in docs/release/CI-2026-10-15.md.
- Ten AI command routes still lack audit catalogue/walk integration; the AI lifecycle category
  remains pending. The nine helper typing errors found during triage were resolved above.

## Verification helper typing — October 15, 2026

- Resolved all nine errors found by the explicit scan of five regression-test modules:
  separate AST owner/callee variables, concrete row mappings, typed route traversal, and
  explicit optional-value assertions. The approval-race test imports the helper from its
  defining module and still patches the production call site.
- Evidence is recorded in docs/release/CI-2026-10-15.md. AI audit catalogue and lifecycle-walk
  integration remain the next known CI gap; full candidate verification is still outstanding.

## AI command audit coverage — October 15, 2026

- Registered all ten AI command routes and added real API scenarios to the shared audit walk:
  settings author/test/submit/withdraw, extraction/explanation requests, proposal accept/reject,
  and the workspace kill switch. Retained synthetic proposal evidence needs no provider call.
- Draft acceptance exposed a missing computation-evidence audit classification; it now names
  the source computation's contract members. Pending-category negative controls remain active
  through a synthetic pending catalogue, with a separate missing-live-AI-evidence assertion.
- Verification evidence is recorded in docs/release/CI-2026-10-15.md. Full candidate acceptance,
  replay orchestration/release admission and independent accounting sign-off remain open.

## Release-validation population reader — October 15, 2026

- Added a tenant-wide, single-statement reader for current heads, open-period member events,
  sealed ledger activity, enabled-book recognition-method strata and member entity ids.
  Partial entity scopes are refused; the reader does not widen caller scope.
- Current membership uses active database rows rather than application-clock comparisons.
  Verification evidence is recorded in docs/release/CI-2026-10-15.md.
- Frozen-attempt persistence, fan-out/handler, dataset publication and release admission remain
  outstanding. This reader does not dispatch jobs or enable releases.

## Frozen validation-attempt persistence — October 15, 2026

- A parent-locked writer saves attempt metadata and selected group/head rows atomically before
  any job dispatch. Retrying the same attempt preserves its seed and selection, including
  NO_SOURCE. A new attempt requires the predecessor to be superseded explicitly.
- The writer records a tenant-level freeze audit event and refuses partial entity scopes,
  cross-tenant lookups, seed changes, skipped attempt numbers and active predecessors.
- Exact verification is recorded in docs/release/CI-2026-10-15.md. The orchestrator still needs
  replay-seed configuration resolution, supersession/start commands, fan-out/handler, dataset
  publication and release admission. No release is enabled by freezing an attempt.

## Configured replay seed — October 15, 2026

- Added platform.replay_seed to the tenant configuration registry with default 20260912 and
  signed-bigint validation. Revision 0162 seeds existing databases without deleting historical
  catalogue metadata on downgrade. New attempts resolve configuration; retries keep their seed.
- Corrected the missing composite primary-key declarations for the three validation tables in
  the data model. Exact migration, attempt and schema evidence is in docs/release/CI-2026-10-15.md.
- Supersession/start orchestration, replay fan-out/handler, dataset publication and admission
  remain outstanding. This setting does not enable a release or deploy anything.

## Validation start and full-population fence — October 15, 2026

- Frozen attempts now retain a versioned full-population fingerprint, including unsampled
  heads and current member stream versions. Start refuses population drift or legacy attempts
  lacking that fingerprint, and atomically marks parent/attempt RUNNING with an audit event.
- A matching running retry is read-only; final acceptance still needs a fresh population check.
  Verification is recorded in docs/release/CI-2026-10-15.md.
- Supersession, replay fan-out/handler, datasets and release admission remain unfinished.

## Unapproved validation attempt supersession — October 15, 2026

- Added audited, idempotent supersession under the same parent/attempt locks as result writers.
  Replacement selection can share its transaction; historical selections and evidence remain.
- Linked approvals and non-retryable parent states fail closed. The release approval subject,
  stale-approval invalidation, fan-out, replay handler and final admission remain outstanding.
- Verification evidence is recorded in docs/release/CI-2026-10-15.md.

## Replay identity checks before comparison — October 15, 2026

- Reproduced six wrong source/executed identities that candidate normalisation previously
  reported MATCH. Both replay paths now bind versions, trace versions and input hashes before
  comparison; input codec/source disagreement also fails as an integrity incident.
- Legitimate cross-version comparison remains supported. Test evidence is in
  docs/release/CI-2026-10-15.md. Replay handler/fan-out and release admission remain unfinished.

## Frozen replay evidence reader — October 15, 2026

- Added a worker evidence reader bound to the persisted execution, running attempt and frozen
  source. It checks tenant/task/release/scope before file access and never rebuilds missing input.
- File metadata disagreement reaches the verifier as an integrity mismatch. Storage failures
  propagate; acceptance still rechecks the head and attempt under locks.
- Handler/fan-out, approval resolution and admission remain unfinished. Verification evidence
  is recorded in docs/release/CI-2026-10-15.md.

## Frozen replay execution service — October 15, 2026

- Connected source loading, pure replay and atomic result persistence. The engine runs outside
  database units; committed results are reused before evidence access or re-execution.
- NO_SOURCE records absence without execution. ERROR evidence stays unaccepted for scheduler
  retry handling; changed heads are refused at persistence. Verification is in the CI record.
- Scheduler adapter/state transitions, fan-out, approval resolution and admission remain open.

## Replay worker lifecycle — October 15, 2026

- Registered REPLAY_VERIFY with frozen group binding, audited RUNNING/RETRYABLE transitions,
  three-attempt retry policy, required exhaustion cleanup and cancellation hooks.
- Cancellation fences acceptance; its guard uses a nonblocking job-unit lock to avoid waiting
  on a worker commit, and refuses cancellation after acceptance. Registry checks also corrected
  the stale AI_SETTINGS_VERSION phase inventory. CI evidence is in the dated release record.
- Fan-out, aggregation/artifact publication, approval resolution and admission remain open.

## Frozen validation job fan-out — October 15, 2026

- Added transactional job binding for each frozen selection, with population/release checks
  and reuse of existing jobs on retry. Lost dispatch recovery and concurrent callbacks create
  one queue entry; rollback leaves no partial bindings. No sample is redrawn.
- Seven fan-out database cases and 17 scheduler regressions passed, alongside unit/architecture,
  typing and lint checks. Evidence: docs/release/CI-2026-10-15.md.
- Aggregation, artifacts, approval resolution and final admission remain open.

## Validation aggregate refusal checks — October 15, 2026

- Reproduced and fixed ERROR evidence counting toward a pass in the pure aggregator. It now
  makes an otherwise terminal attempt INCOMPLETE, including alongside MAJOR differences.
- PATCH validations are refused before population evaluation. All 22 aggregation/state-machine
  tests and typing passed; dated CI evidence records the checks. Persisted job aggregation,
  artifact publication, approval resolution and admission remain unfinished.

## Persisted validation assessment — October 15, 2026

- Added assessment of frozen selections, accepted evidence and actual child-job completion
  under validation/attempt locks. Changed populations or incomplete selections are refused.
- Accepted evidence while its job still runs remains pending; cancellation and exhausted
  retries make the assessment INCOMPLETE. The assessment makes no enablement transition.
- Database lifecycle verification and typing/lint evidence are in the dated CI record.
  Dataset/report publication, final acceptance, approvals and admission remain outstanding.

## Encrypted validation artifact storage — October 15, 2026

- Added VALIDATION_DATASET purpose/migration, per-file encryption and internal-only owner
  rules for attempt datasets and verification difference datasets. Generic file routes deny
  reads; existing non-overridable evidence holds protect referenced artifacts.
- Database encryption/read/hold and empty migration round-trip tests passed, with file-access,
  policy and registry checks. CI evidence is in the dated release record.
- Dataset production, report publication, final acceptance, approvals and admission remain open.

## Retained replay difference details — October 15, 2026

- Candidate comparisons now carry full difference rows and check them against their summary.
  Persistence stores an encrypted, identity-bound difference artifact in the same transaction
  as the result and accepted pointer, including an explicit empty comparison for MATCH.
- Rollback, retry reuse, encryption, evidence holds and generic download denial passed database
  checks. Unit/typing evidence is in the dated CI record. Historical results are not backfilled.
- Attempt datasets, reports, final acceptance, approvals and admission remain unfinished.

## Frozen attempt dataset publication — October 15, 2026

- Added terminal-job dataset assembly from frozen selections and retained comparisons. It
  verifies artifact identities, digests and detail counts; failed and no-source rows remain.
- Dataset reference and COMPLETE/INCOMPLETE attempt status commit together. Retries read the
  original file; rollback leaves neither the reference nor a completed attempt. Parent release
  enablement is unchanged. Lifecycle/integrity verification is in the dated CI record.
- Report publication, final population acceptance, approvals and admission remain unfinished.

## Authorized validation report source — October 15, 2026

- Added a retained-dataset reader that checks current report.run permission across the full
  frozen entity set before file access. Partial entity selection, wrong tenant and mismatched
  rerun file/hash bindings are refused; SYSTEM has no implicit reader grant.
- Dataset metadata, digest, canonical JSON, source identity and record cutoff are checked.
  Matching/differing report data reproduces after later contract activity; database and typing
  evidence is in the dated CI record. Report catalogue/job integration remains unfinished.
- Final acceptance, approvals and admission also remain open; no deployment.

## Bound upgrade-validation report builder — October 15, 2026

- Added the report builder over the verified dataset, typed change-count columns and canonical
  text for structured before/after values. Its source binding records the exact file, hash,
  attempt and frozen entity set; reruns rebuild rows rather than reuse cached output.
- JSON/CSV reproducibility and requester-grant checks passed database tests. Unsupported modes
  and incomplete/incompatible bindings fail before evidence reads. Dated CI evidence records
  the checks. Catalogue/job registration and requester reload wiring remain unfinished.
- Final acceptance, approvals and admission remain open; no deployment.

## Validation report catalogue and worker integration — October 19, 2026

- Registered upgrade_validation and its retained-source contract, with migration 0164.
  Jobs reload the human or API-client initiator and enforce current report/export grants
  over the complete frozen entity population before reading or publishing evidence.
- Actual JSON/CSV jobs and reruns passed, including API-client revocation and retry exhaustion
  without output. Required report parameters now fail validation when absent. Catalogue,
  framework, typing and lint evidence is in CI-2026-10-19.md.
- Official attempt report attachment, final acceptance, approvals and admission remain open.
  Repository work only; no deployment or independent accounting sign-off.

## Verified attempt report attachment — October 19, 2026

- Added transaction-bound report attachment under parent/attempt locks. It requires a
  completed report job for the exact attempt, rechecks caller permissions, rebuilds frozen
  source rows/totals, and verifies the output binding and file integrity before attachment.
- The reference is write-once. Retries recheck evidence without updating the row; rollback,
  replacement refusal, revoked access and corrupted output are covered by database tests.
- Final population acceptance, approval routing and admission remain unfinished. Attachment
  is an internal operation awaiting final orchestration; it never enables the release.

## Completed-attempt population reassessment — October 19, 2026

- Assessment now accepts COMPLETE/INCOMPLETE attempts while the parent remains RUNNING.
  It rechecks the full population fingerprint and actual job outcomes, requires retained
  dataset references and rejects lifecycle/outcome disagreement.
- Matching/differing completed attempts retain their decisions until contract activity changes;
  changed populations fail reassessment while the original audit reports remain reproducible.
  Cancellation and retry exhaustion remain INCOMPLETE after dataset publication.
- Final acceptance still needs report verification, concurrent population-writer fencing,
  approval routing and admission integration. This change performs no release enablement.

## Tenant population transaction fence — October 19, 2026

- Migration 0165 adds shared transaction guards to writes on all 12 population-reader
  tables and their partitions. The acceptance helper reserves the tenant exclusively;
  conflicts refuse immediately and map to retryable lock-conflict responses.
- Database checks cover concurrent shared writers, both contention directions, commit/
  rollback release, tenant isolation, trigger/partition coverage, migration round-trip and
  existing validation/report workflows. Six cases passed; typing and lint also passed.
- Final acceptance must acquire the fence before validation locks and reread under READ
  COMMITTED. The helper is not yet connected to final acceptance or approval/admission.

## Upgrade processing event schema — October 19, 2026

- Migration 0166 adds the tenant-isolated, append-only release_group_processing event log
  per group/entity/book portion, reusing the existing processing-state enum. Its privacy
  catalogue entry is reconciled with the implemented schema.
- Guards require the accepted attempt of an enabled upgrade, valid initial portions,
  sequential events, preserved prior postings and bound computation/posting evidence.
  Outcome checks distinguish deferrals, posted portions and verified no-posting settlement.
- Migration, database schema and lifecycle probes passed; details are in the dated CI record.
  Automatic seeding, computation persistence, posting attribution and final acceptance remain
  unfinished. No deployment or independent accounting sign-off occurred.

## Atomic upgrade processing queue seed — October 19, 2026

- Added seeding of every current group/entity/enabled-book portion after an accepted upgrade,
  under the tenant population fence. It checks the accepted attempt's population before the
  first write and commits initial PENDING events with a write-once count/digest manifest.
- Retries verify retained initial rows without drawing today's population; partial rows without
  a manifest are refused. Migration 0167 seals the initial queue against later additions.
- Database checks cover unsampled groups, empty populations, rollback, manifest immutability,
  retries after activity and migration round-trip. Final acceptance and approval/admission
  integration remain unfinished; callers must accept and seed in the same transaction.

## Immutable posting attribution schema — October 19, 2026

- Migration 0168 adds tenant-isolated, append-only posting_attribution with one row per
  posting. Inserts require the accepted, enabled release and an unsettled processing group,
  matching posting/computation ownership and valid cause-comparison metadata.
- Processing events and attribution share a nonblocking group transaction guard so their
  checks cannot race settlement. Privacy and sandbox snapshot inventories are reconciled.
- Database probes cover attribution, duplicate/mutation/unsupported-cause refusal, terminal
  groups, contention and migration round-trip. Persistence/report integration remains open,
  alongside final acceptance, approval routing and admission. No deployment.

## Atomic upgrade computation persistence — October 19, 2026

- Computation persistence now writes posting attribution and append-only portion outcomes in
  the same transaction as postings and head updates, under the shared upgrade-group guard.
- Attribution checks retained predecessor input integrity and records actual posting origins;
  unavailable historical inputs retain the conservative context label. Exact replay adds no rows.
- Database probes cover first computation, no-posting recomputation, changed billing,
  corrupted input refusal and rollback. Full computation regression results are recorded in CI.
- Deferred portion handling uses the existing conservative origin rule; runtime closed-period
  and period-open rescheduling coverage remain outstanding, as do the true-up register,
  final acceptance, approval/admission integration and independent accounting sign-off.

## Release acceptance and independent approval — October 19, 2026

- Added finalization from an attached frozen report: matching results enable and seed atomically;
  MINOR differences fail; MAJOR differences create a SYSTEM-prepared independent approval.
- Approval binds the frozen dataset, population and entity set, rechecks current population,
  enables/seeds atomically and dirties only DIFFERENCES groups while preserving prior stamps.
  Rejection keeps the release disabled; stale/withdrawn reviews return it to INCOMPLETE.
- Pending approval supersession now voids STALE_SUBJECT and permits a replacement attempt.
  Revision 0169 adds the approval type and stale-review transition. Existing approval API,
  inbox labels, generated schema and report filters recognize the new subject.
- Targeted checks are recorded in the dated CI log. Release preparation/automatic orchestration,
  baseline/bootstrap handling, computation admission and the true-up register remain development
  priorities; current-candidate release verification and independent accounting sign-off remain open.

## Tenant release creation and resumable API — October 19, 2026

- Added authoritative tenant validation creation: empty tenants bootstrap; historical tenants
  require preparation; skipped stronger releases retain their level; downgrades are refused.
- Added POST /release-validations/current/advance with all-entity report permission and command
  idempotency. It resumes frozen replay jobs, JSON reports, attachment and final acceptance;
  MAJOR differences enter independent approval. Repeated calls reuse persisted work.
- Seven focused database cases passed, including the actual API/replay/report/enable path.
  Generated API and frontend types are updated. Detailed usage and evidence are in CI-2026-10-19.
- This is caller-driven advancement. Automatic scheduling, explicit baseline preparation,
  computation admission and the true-up register remain development priorities. No deployment.

## Event BI extract and reporting backlog — October 19, 2026

- Registered extract_events with fixed schema v1, explicit entity scope, inclusive source cutoff,
  exclusive incremental start, contact redaction and retained-input rebuilds. Added JSON/CSV
  metadata and CSV byte-hash manifests; source time stays fixed across worker execution.
- Added report-page full/incremental controls and documented field types and operating limits.
  Actual API/worker delivery, incremental validation and rerun passed; existing viewer checks
  and focused Python/frontend typing passed. Evidence is in CI-2026-10-19.md.
- Reporting remains a development priority: 16 catalogue definitions still lack builders.
  Extract lock snapshots, previous-run watermark defaults and true-up register remain open.
  No deployment; no claim of reporting or production-readiness completion.

## Contract version BI extract — October 19, 2026

- Added extract_contract_versions v1: all versions in one book, fixed source cutoff,
  created-time incremental window, exact decimal strings and original computation members.
  Partial combined-entity scope is refused; membership reads are batched.
- Registered retained-input rebuilds and JSON/CSV metadata; existing extract controls expose
  the report. Migration 0170 reconciles disclosed query sources. User guide documents types.
- Actual delivery and rerun checks pass alongside event-extract regression. Reporting still
  has 15 catalogue definitions without builders; locked extracts and true-up remain unfinished.
  Evidence is in CI-2026-10-19.md. No deployment or readiness claim.

## Obligation BI extract — October 19, 2026

- Added extract_obligations v1 with latest-per-contract chain selection, all book statuses,
  explicit created/known cutoff and incremental created-time filtering. Former group versions
  do not duplicate contracts, and after-cutoff candidates cannot displace earlier versions.
- Exported fixed typed columns and exact decimal strings, with per-currency allocation and
  cumulative-revenue sums. Registered JSON/CSV delivery and retained-source reruns; existing
  extract page controls expose the report. User guide states snapshot-delta semantics.
- Reporting remains open: 14 catalogue builders missing, six of them extracts. Locked extracts,
  watermark defaults, true-up and live browser acceptance remain unfinished. No deployment.

## Schedule line BI extract — October 19, 2026

- Added extract_schedule_lines v1 over latest per-contract versions, scoped by schedule entity,
  with period and contract identifiers. Known/created cutoffs and incremental line creation
  windows use the SQL chain reader. Row identity includes the source partition date.
- Registered JSON/CSV metadata and retained-input rebuilding; exact decimal values and
  per-currency amount totals use existing extract page controls. User guide documents types
  and snapshot-delta semantics. Targeted evidence is in CI-2026-10-19.md.
- Reporting remains unfinished: 13 missing builders, five of them extracts. Locked extracts,
  automatic watermarks, true-up and live browser acceptance remain open. No deployment.

## Contract balance BI extract — October 19, 2026

- Added extract_balances v1 over latest per-contract versions, scoped by balance entity.
  Fixed columns preserve transaction/functional currency amounts, with contract/entity labels.
- Registered full/incremental JSON/CSV delivery and retained-input reruns. Control totals group
  contract liability, contract asset and unbilled receivable by functional currency. Existing
  extract controls expose the report; the guide states field types and snapshot-delta semantics.
- Reporting remains open: 12 missing builders, four of them extracts. Locked datasets,
  automatic watermarks, true-up and live browser acceptance remain unfinished. No deployment.

## Sealed subledger BI extract — October 19, 2026

- Added extract_subledger_lines v1 with explicit business/server recording and server seal
  cutoffs, entity/book scope, exact decimals and retained contract/period/account labels.
- Added JSON/CSV metadata and per-currency plus entity/book/currency/period control totals.
  Registered source retention and reruns; migration 0171 updates disclosed query sources.
- Actual API checks cover CSV hash, grouped balance, incremental selection, pre-seal exclusion
  and reproduction. Evidence is in CI-2026-10-19.md. The guide explicitly distinguishes
  recorded-time incremental output from commit-time change capture.
- Reporting remains open: 11 missing builders, three of them extracts. Locked datasets,
  watermark defaults, true-up and live browser acceptance remain unfinished. No deployment.

## Legacy Contract_Live BI extract — October 19, 2026

- Added extract_legacy_contract_live v1 over all effective dates of ASC606 history with
  creation/source cutoffs and incremental row selection. Other books are refused explicitly.
- Preserved the 71-column formatter and original exact trace texts. Retained current and
  predecessor inputs supply reruns without querying today's history. CSV/JSON metadata and
  source contracts are registered; migration 0172 reconciles disclosed query sources.
- Actual API checks match the existing legacy history output and verify CSV hash and rerun;
  evidence is in CI-2026-10-19.md. Ten builders remain missing, including contract and journal
  extracts. Locked datasets, watermarks, true-up and browser acceptance remain open.

## Journal line BI extract — October 19, 2026

- Added extract_journal_lines v1 with entity/book scope, source-time lifecycle reconstruction,
  full/incremental creation windows, fixed typed columns and per-currency debit/credit totals.
  A later cancellation does not erase an earlier historical population; unknown state refuses.
- Registered JSON/CSV and retained line/label/lifecycle evidence for reruns. The existing JE
  population shares its transition-history reader. Migration 0173 updates source disclosure.
- Real API cancellation, historical reads, CSV hash, totals and rerun checks pass. Evidence is
  in CI-2026-10-19.md. Nine builders remain missing, including the contract extract; locked
  datasets, watermarks, true-up and browser acceptance remain unfinished. No deployment.

## Contract BI extract and source history — October 19, 2026

- Added extract_contracts v1: fixed header columns, historical customer/entity codes,
  JSON/CSV, creation-time incremental windows and retained inputs for identical reruns.
- Migration 0174 captures contract/header and code changes atomically in append-only source
  revisions; existing rows receive migration-time baselines. Missing earlier coverage refuses.
  Capture time is not commit time; restored sandboxes start new history.
- Actual API export, subsequent contract update, historical read, rerun, CSV hash and database
  capture protections passed. Source disclosure matches the migrated catalogue. Targeted
  inventory/privacy checks and typing passed; details in CI-2026-10-19.md.
- All nine extract builders now exist; eight other catalogue builders remain. Locked datasets,
  watermarks, true-up, broader acceptance and independent accounting sign-off remain open.
  Continue unfinished reporting development; no deployment.

## Bookings/billings/revenue source and aggregation implementation — October 19, 2026

- Implemented scoped, cutoff-bound raw source capture for RPT-37, retaining event identity
  decisions and sealed revenue lines. Billing reuses the engine-aligned invoice identity,
  credit and void handling of the balance rollforward. Revenue preserves posting periods,
  transaction/functional amounts and line identities, including signed reversals.
- Implemented fiscal month/quarter/year presentation, entity/currency splits, signed totals
  and journal-revenue comparison. Missing measure populations or FX valuation refuse.
- Real source reads prove later invoices do not change an earlier cutoff or retained inputs;
  scoped reads and retained scope/book mismatches are exercised. Targeted evidence is in
  CI-2026-10-19.md. No full-suite rerun or deployment.
- RPT-37 is not registered yet: activation-value and applied-modification attribution, FX
  valuation, journal comparator sourcing, contributor routes and end-to-end publication remain.
  Eight reports still lack complete registered builders; do not mark this report finished.

## BBR activated bookings and application value attribution — October 19, 2026

- Added activated-contract values from each contract's own signed booking line consideration,
  with booking/activation provenance. Drafts and voided contracts contribute no new bookings.
  Separate-contract modifications are identified through their applied booking event and
  excluded from the new-contract column, preventing later activation from double counting.
- Added original application-group/version reads and predecessor-based modification price
  differences, retained for rebuilds and counted once per modification, not per obligation.
  Missing predecessors, ambiguous applications and shared valuation causes refuse attribution.
- Real K01 booking value 135,000 and K02 applied modification 60,000 checks pass. Targeted
  evidence and two pre-existing test-module typing findings are in CI-2026-10-19.md.
- BBR still needs FX valuation, journal comparator sourcing, source adapter/registration,
  contributor routes and broader acceptance. Pre-activation changes and shared valuation
  causes need further attribution support; independent accounting sign-off is still absent.
  Eight reports remain without complete registered builders. No deployment.

## BBR report delivery, currency valuation and journal comparison — October 19, 2026

- Registered bookings_billings_revenue in the report framework with functional/month defaults,
  fiscal ranges, scoped sources and retained-input reruns. JSON/CSV use the common report flow;
  standard XLSX/PDF writers are available but were not separately exercised in this slice.
- Added historical approved spot-rate valuation for contract/billing contributions, preserving
  rate/version identities. Posted revenue keeps its stored functional amount. Missing or
  ambiguous rates refuse. Journal revenue uses retained lifecycle evidence at the same cutoff.
- Actual API report, PASS journal tie-out, CSV hash and identical rerun passed; migration 0175
  reconciles IPE source disclosure. Evidence is in CI-2026-10-19.md.
- Seven catalogue definitions still lack registered builders. BBR contributor cell routes,
  reporting-currency and lock datasets, complex/shared attribution, cross-currency database
  acceptance, browser acceptance and independent accounting approval remain open. No deployment.

## BBR cell contributions and business-record navigation — October 19, 2026

- Retain valued pre-aggregation contributions beside the original raw sources. All four BBR
  money cells rebuild their amounts from those inputs and list source IDs and contributions.
  New contract-event/modification owner rules use the existing reader-scope redaction path.
- Enabled four drills in the report grid. The contributor panel links business records to
  contract history/billing, modification detail or contract journals; it does not send these
  records to unsupported calculation-graph routes. Source IDs remain visible.
- Actual API revenue totals, zero cell, new booking and billing contributions pass; a later
  invoice does not change an earlier report's contributions. Frontend drill/link tests pass,
  as do frontend typing and targeted backend typing/lint. See CI-2026-10-19.md.
- Seven report builders remain missing. BBR complex attribution, locked/reporting-currency
  sources, wider scope/modification-cell/browser acceptance and accounting sign-off remain open.
  Existing BBR runs without aggregation evidence refuse a drill instead of reading live data.

## BBR actual FX admission fix; forecast dependency audit — October 19, 2026

- Fixed a real cross-currency defect: BBR matched `SPOT`, while E-51 and approved database
  rate rows use `spot`. Both live and retained readers now use RateType.SPOT.value. The old
  authored uppercase fixture masked the mismatch and has been corrected.
- Actual API-created, submitted and independently approved spot versions now exercise BBR:
  100.01 EUR × 1.2345 = 123.46 USD; after approval of 1.3000 the old cutoff still uses v1 and
  the new cutoff uses v2 (130.01 USD), preserving the exact version identities.
- Forecast audit found no implemented scenario/event-set/run tables or domain runtime; these
  are still pending in privacy/snapshot catalogues and FCS-1 to FCS-3. Forecast reports require
  that foundation before a genuine output builder. No forecast implementation is claimed yet.
- Seven report builders remain unregistered; count does not represent the size of the forecast
  subsystem work. Independent accounting sign-off and broad acceptance remain open. No deployment.

## Forecast persistence foundation; reporting backlog retained — October 19, 2026

- Migration 0176 adds scenario, versioned forecast_event_set, forecast_run and deal_preview,
  with tenant-bound keys/RLS, sandbox guards, published-input freeze, terminal run freeze and
  write-once preview save linkage. Privacy and snapshot inventories now include these tables.
- This is schema groundwork only. Scenario creation/refresh APIs, input replay, forecast jobs,
  output builders and UI remain unfinished; FCS-1 is not complete.
- Reporting priorities remain: forecast_outputs, actual_vs_forecast, parallel_run_comparison,
  variance_between_closes, contract_sample_pack, period_evidence_pack and disclosure_pack.
  Separately, engine_trueup_register and existing-report acceptance gaps remain open.
- Focused verification: PostgreSQL migration round trip and installed RLS/transition bodies pass;
  database lint passes; privacy/snapshot checks: 76 passed. Architecture replay: 68 passed,
  5 failed at the existing multiline CHECK parser in migration 0166, before 0176; not waived.
- No deployment, forecast execution, financial acceptance or production-readiness claim.

## Scenario catalogue API and refresh-compatible pointer — October 19, 2026

- Added GET /scenarios with scenario.use authorization across the tenant, status filtering,
  stable cursor pagination and named creator output. Tenant identity/internal actor fields are
  omitted. OpenAPI and frontend API types regenerated.
- Migration 0177 removes the unintended immutable scenario_tenant_id check from 0176: FCS-2
  refresh must be able to replace the sandbox. Production/source-sandbox relationship checks
  remain; this migration does not implement refresh or permit cross-production targets.
- Actual HTTP check covers denial without permission, populated ACTIVE/ARCHIVED listing,
  status filtering and exclusion of another tenant's scenario. Together with forecast migration
  round trip: 2 passed (7.70s). Ruff, mypy (4 files) and make openapi passed.
- Scenario creation, archive, refresh, creator grants, event-set replay and forecast jobs are
  still absent. No browser workflow or refresh business acceptance claimed. Seven missing
  report builders and engine_trueup_register remain outstanding; no deployment.

## Asynchronous scenario creation and creator access — October 19, 2026

- POST /scenarios now accepts name, purpose and optional known_at, returns a TENANT_SNAPSHOT
  job with preallocated scenario/snapshot ids, and registers the source scenario only after the
  sandbox copy succeeds. Completion audits both tenants; job results link to the scenario list.
- Preserves copied memberships. A creator absent from the historical snapshot receives only
  Viewer plus a dedicated scenario.use role before period replay; inactive copied membership
  refuses. Scenario sandbox codes use the allocated tenant id so equal names do not collide.
- scenario.use does not inherit tenant.snapshot's step-up requirement; the ordinary snapshot
  command still enforces it. Purpose input is limited to the database memo's 4000 characters.
- Actual API + worker checks: copied creator, historical snapshot without creator (minimum grants),
  idempotent request replay, source/sandbox audit records, populated tenant-isolated listing,
  and ordinary snapshot permission/step-up regression: 4 passed, 4 deselected (10.92s).
  Ruff, mypy (10 files), make openapi passed; generated frontend API types updated.
- These are empty-business-data copies, not the Q4 world with contracts and closed periods.
  Closed-period replay for a requester with only scenario.use, nonempty determinism, worker
  interruption/failure boundaries, archive, refresh, event sets, forecasting and UI remain open.
  FCS-1 is not complete and no forecast report builder is newly delivered. No deployment.

## Scenario archive and read-only command/worker gate — October 19, 2026

- Added POST /scenarios/{id}/archive with row ETag, creator or tenant-wide Controller admission,
  replay authorization, pending-job refusal and atomic audit records in source and sandbox.
  The sandbox remains ACTIVE/selectable for reading; its source scenario becomes ARCHIVED.
- HTTP commands check the exact source scenario before cached replay and acquire a shared lock
  during business transactions. Worker attempt units of work use the same gate; operational
  failure settlement remains possible. This source-row lock orders normal writes against archive.
- Migration 0178 freezes archived scenario fields and forbids reactivation. The scope trigger
  rechecks sandbox provenance only when its pointer/source changes: a Controller need not also
  hold a membership in the sandbox merely to archive an existing relationship.
- Actual API/worker + migration checks: creator/Controller archive, non-owner denial, queued-job
  refusal, successful archive replay, rejected replay of a formerly successful sandbox write,
  retained reads, delayed worker refusal with FAILED settlement/no business audit, mirrored
  archive audit, migration round trip and ordinary saved-view regression: 5 passed (11.26s).
  Ruff, mypy (7 files), OpenAPI/types generation passed.
- Concurrent races across every custom write path and direct copy transaction are not yet
  acceptance-tested. Nonempty/closed-period scenario copy, refresh, event sets, forecast runs,
  report builders and UI remain open. No production-readiness or deployment claim.

## Versioned forecast input set API — October 19, 2026

- Added scenario-only GET/POST /forecast-event-sets, GET/PATCH by id, and publish. Drafts carry
  ordered upload/command fields, source scenario linkage and row ETags. New versions retain the
  previous version reference and input arrays; one draft per code is admitted under a code lock.
- Migration 0179 installs a forecast-specific DRAFT -> PUBLISHED -> SUPERSEDED lifecycle with
  DB-04 immutable publication contents/stamps and one published version per tenant/code.
  Publishing hashes canonical content and atomically supersedes the old version. No production
  approval request is fabricated; shared production configuration approval rules are unchanged.
  This scenario-specific rule is now explicit in T-FC-02.
- Actual HTTP checks inside both created-scenario membership cases cover production refusal,
  request replay, draft edit, stale ETag rejection, publish, API/direct-SQL publication freeze,
  version 2 publication, retained old hash and published-only listing. With the scenario flow
  and empty migration round trip: 4 passed (12.75s). Ruff, mypy (5 files, explicit package bases)
  and OpenAPI/types generation pass. Existing OpenAPI paths/operations are unchanged.
- FCS-2 remains incomplete: no committed-import linkage, automatic recording of successful
  business commands, ordered input replay or refresh yet. These APIs currently manage input-set
  versions; they do not execute or populate forecasts. Forecast runs/output and UI remain open.
  Seven missing report builders remain missing. No deployment or readiness claim.

## Frozen monetary changes for re-lock evidence — October 19, 2026

- Added contract/currency comparison of frozen revenue, contract liability, contract asset plus
  unbilled receivable and disclosed RPO. Exact arithmetic retains both lock/file identities and
  contributing row keys; currencies remain separate and exempt RPO is excluded.
- Re-lock evidence now includes `relock/frozen_measure_changes.json` beside the verified original
  stored comparison. Rejects mismatched/unordered locks, missing sources, corrupt bytes and
  invalid/duplicate monetary rows. No current-contract values or guessed driver attribution.
- Focused monetary/source checks: 23 passed; real lock/reopen/re-lock path: 1 passed. Ruff passes;
  the two implementation modules and new test pass Mypy. The two existing integration test files
  have seven Mypy errors also reproduced from HEAD; they are not new and remain outstanding.
- RPT-38 remains incomplete: ordered DRY_RUN driver replay, report registration/formats, cell
  explanations, browser and K-03 financial acceptance still required. Seven missing report
  builders remain unregistered. No deployment or accounting/production-readiness claim.

## Event-only close variance replay — October 19, 2026

- Added the DRY_RUN execution core: ENG-06 event order, maximal driver runs, separate time
  progression, exact reconciliation to both frozen monetary endpoints and execution provenance.
  Endpoint mismatch refuses; no balancing OTHER residual. Inputs remain unchanged.
- Real engine: two late invoices move contract liability from 20 to 170, with 150 assigned to
  LATE_EVENT and both event identities retained. Nine focused tests, Ruff and Mypy pass.
- This is not wired to a report/job yet. Authorized retained source loading, complete monetary
  projection, reference/FX/membership/posting-basis replay phases and RPT-38 report/UI remain
  required. Changed reference inputs and unsupported event classifications currently refuse.
  Seven missing report builders remain unregistered. No deployment or readiness claim.


## Fixed-period variance revenue/balance projection — October 19, 2026

- Connected event replay to a server-owned monetary projection for recognized revenue, contract
  liability and contract asset plus unbilled receivable. Revenue is signed posted basis plus
  posting intents in the selected posting period; schedules never substitute for revenue.
- Transaction/functional views use exact minor-unit conversion. Missing monetary values,
  inconsistent currencies, unknown subjects and duplicate balance identities refuse.
- Real-engine late-invoice replay now uses this adapter. Fifteen focused checks, Ruff and
  Mypy pass. Dated RPO is explicitly unsupported by this entry point, not silently omitted.
- Retained source loading, RPO projection, other replay phases and report/job/UI integration
  remain required. Seven missing report builders remain unregistered. No deployment/readiness claim.



## Dated RPO in close variance replay — October 19, 2026

- Connected RPO through the existing dated trace reader: selected period-end scheduled/awaiting
  remainder, disclosure-entry/status checks and retained duration/right-to-invoice exemptions.
  The projection now receives each executed input bundle, including new activation events.
- Real engine: May delivery leaves April RPO at 795, moves May RPO to 736.16, and attributes
  revenue +58.84/RPO -58.84 to LATE_EVENT. Activation, duration exemption and missing-trace
  cases are covered. Nineteen focused tests, Ruff and Mypy pass; no database writes in projection.
- Amount-specific VC exemptions and foreign functional RPO remain unsupported and refuse.
  Retained-source loading, other replay phases, report/job/UI and financial acceptance remain
  required. Seven missing report builders remain unregistered. No deployment/readiness claim.

## Retained inputs for close variance — October 19, 2026

- Added the source read phase: complete frozen closes, historical per-contract computation
  candidates, original evidence verification and whole-group entity authorization. Required
  access entities accompany the result. Missing retained evidence never uses current inputs.
- Filter computation availability before latest-version selection: a later recompute with no
  new event must not replace the computation available at an earlier close cutoff.
- Monetary frozen reads use report.run; evidence packs retain their extra audit.read requirement.
  Five focused frozen-source checks and one retained-computation selection check pass; the latter
  uses a population shell, not a full close. Source Mypy and changed-file Ruff pass.
- Candidate selection is not endpoint reproduction. Job integration, operational input
  normalization, other replay phases, report/UI and accounting acceptance remain required.
  Seven missing report builders remain unregistered. No deployment/readiness claim.

## Retained computation execution for close variance — October 19, 2026

- Added the transaction-free execution phase: original retained inputs must reproduce their
  output hashes and monetary endpoints before DRY_RUN. Common earlier posted amounts and
  previous stream heads are explicit counterfactual adjustments, with original source hashes
  and normalized input identity retained. The final replay must match later frozen money.
- Identical saved computations produce a zero-change result without inventing a later cutoff.
  Reference/calendar/FX changes still refuse. Actual first recomputation adds recorded SSP
  policies, demonstrating a remaining reference-replay requirement rather than a posting change.
- Real-engine carried-posting/delivery, retained hash/endpoint refusal and same-source checks:
  20 passed. Actual database source selection/reuse: 1 passed. Ruff and source/test Mypy pass.
- Group aggregation, reference replay, job/report registration, output formats, UI and full
  frozen-close accounting acceptance remain outstanding. Seven builders remain unregistered.

## Multi-group close variance and SSP readback — October 19, 2026

- Added the pure multi-group execution phase over an authorized frozen pair: every monetary
  contract must have a source, groups select one computation each, and exact driver totals
  retain currency/measure identity and each group's execution evidence. Missing, new, removed
  or regrouped populations refuse until explicit population replay is implemented.
- First-compute SSP readbacks now normalize only when the new recorded version exactly matches
  the earlier reproduced obligation's selected SSP version. Existing choices, overrides,
  mismatched versions and modification-weight readbacks retain reference-replay requirements.
- Actual consecutive persisted computations now reconcile with posted/head/readback adjustments.
  Two real-engine groups reconcile revenue +117.68 and RPO -117.68 against authored frozen CSVs;
  this is not a full close workflow. Replay suite 21 passed, reference guards 4 passed, database
  selection/execution 1 passed; changed-file Ruff and source/replay-test Mypy pass.
- Report registration/job/formats/UI, wider reference/FX/population phases and full frozen-close
  accounting acceptance remain open. Seven builders remain unregistered; no deployment.

## Close variance report dataset and contributor evidence — October 19, 2026

- Added presentation over reconciled group replay: Change by driver and Changes by contract,
  all four monetary measures, signed earlier/later/change values, currency-qualified row keys
  and control totals. Billing remains an explicit driver rather than being relabeled Other.
- Report evidence retains both lock identities/times/file hashes, group computation/input/output
  hashes, normalized fields, replay executions, source rows and contributing event identities.
  Summary cells retain their contract contributions. Endpoints, group identity, access scope and
  driver totals are rechecked; sub-minor-unit money refuses rather than silently rounding.
- Real-engine two-group fixture exercises the dataset, CSV/XLSX/PDF writers and JSON-safe
  evidence; both lock IDs are supplied to the standard export stamp. Source/replay-test Mypy
  and Ruff pass. This is an authored frozen-data fixture, not a full close/report API journey.
- Report registration remains pending: the current framework runs builders inside its DB
  transaction. RPT-38 needs authorized read, transaction-free compute and reauthorized publish
  phases, source binding/rerun and cell routing before exposure. UI/header polish, wider replay
  phases and accounting acceptance remain open. Seven builders remain unregistered; no deployment.

## Registered close variance worker — October 19, 2026

- Registered variance_between_closes with an adapter source contract. Creation authorizes both
  frozen locks and complete retained groups; stored run scope includes every required entity.
  Locks unavailable at the requested cutoff refuse. No schema/API shape change is required.
- REPORT_RUN now reads/authorizes, closes its UOW, computes with attempt-fenced heartbeats,
  then reopens a UOW and reauthorizes before rendering/storage. The builder compares original
  source identities again. Same-source reruns reread and recompute; no saved-output replay.
- Source bindings retain lock manifests, contract/computation mappings, runtime/input/output
  identities, complete entity requirements and contributor evidence. Direct in-transaction
  calls without the phased calculation result refuse.
- Seeded empty locks with real snapshot files: actual job/output/rerun passes; an injected
  post-compute permission loss prevents output publication. The calculation hook proves all
  read sessions are outside transactions. Both cases pass; existing report/rerun regression,
  catalogue/source-contract checks, source Mypy and changed-file Ruff pass.
- Six catalogue builders remain unregistered. RPT-38 still needs populated close-to-report
  financial acceptance, cell explanation routing, UI/header polish, wider reference/FX and
  new/regrouped contract replay. No production readiness or deployment claim.

## Close variance cell explanations and viewer sections — October 19, 2026

- Connected Change cells in both variance sections to retained contributor evidence. Contract
  amounts reconcile exactly; identity/hash/scope checks bind them to original groups, and SQL
  resolves contracts only through the retained computation/book. A run effect is not split into
  invented per-event amounts. Current contributor visibility applies to contract records.
- Added optional plain-text contributor details: contract name, drivers, event keys, both lock
  IDs and source-row keys where available. The viewer links to internal contract history.
  OpenAPI/client types are regenerated. Older evidence without cell facts refuses by name.
- Fixed numeric section routing; exports retain readable section labels. Both sections expose
  only Change as drillable and hide internal measure/driver fields. Reruns refresh derived
  contributor evidence while still validating and recomputing the original source identities.
- Real-engine replay/presentation suite: 25 passed, including cell arithmetic/hash refusal with
  a lookup seam (not an HTTP/DB cell journey). Worker/rerun/permission-loss regression: 2 passed;
  frontend variance/BBR checks: 3 passed. Mypy, tsc, Ruff, ESLint and make openapi pass.
- Six catalogue builders remain unregistered. Populated close-to-report/cell browser acceptance,
  headers/empty-state polish, broader reference/FX/population replay and accounting sign-off
  remain open. No deployment or production readiness claim.

## Close variance header, totals and empty state — October 19, 2026

- Added earlier/later lock timestamps and copyable IDs to the report header, from hash-checked
  retained evidence. Export source labels name both locks; the viewer says Frozen close comparison.
- Both sections show separate totals by measure and currency; revenue and RPO cannot cancel each
  other in a shared footer. Identical frozen figures retain zero rows and explicit no-change copy.
- Fixed column ordering and added optional lock_comparison API metadata; regenerated client types.
- Targeted real-engine presentation: 1 passed; worker/rerun and permission-loss: 2 passed after
  correcting SQL result materialization. Frontend: 3 passed; Ruff, Mypy, tsc and ESLint pass.
- Remaining report development: actual_vs_forecast, forecast_outputs, parallel_run_comparison,
  contract_sample_pack, period_evidence_pack, disclosure_pack, and engine_trueup_register.
  Wider variance replay and populated close/cell/browser accounting acceptance remain open.

## Engine true-up register — October 19, 2026

- Implemented and registered engine_trueup_register (migration 0180): latest processing portions
  at exact known_at, unresolved origin periods, sampled flag and actual attributed sealed lines.
  Signed transaction/functional amounts remain separate by entity/book/period/currency/account role.
- No-posting portions carry no invented amounts. A deferred portion remains deferred even when
  it has postings. Whole-group terminal is withheld when an entity is outside the selected scope.
- Retained input facts and hash supply same-source reruns. Workers reload current report/export
  grants. JSON/CSV/XLSX use the normal report pipeline; viewer uses readable ordered column metadata.
- Real computation cases: 3 passed (posted and no-posting outcomes); CSV worker plus bound rerun:
  1 passed; database catalogue: 6 passed; catalogue/source contract: 23 passed; deferred/multicurrency
  arithmetic and missing-attribution refusal: 1 passed. Type/lint checks pass.
- Six catalogue builders remain: actual_vs_forecast, forecast_outputs, parallel_run_comparison,
  contract_sample_pack, period_evidence_pack and disclosure_pack. Full upgrade lifecycle,
  deferred-period reopening, cross-entity browser acceptance and accounting sign-off stay open.

## Parallel-run comparison calculation and viewer — October 19, 2026

- Added parallel_comparison.compare for independently produced journal and contract-balance
  snapshots. Both sources must declare complete entity/book/currency period coverage and retained
  identities. Missing coverage is excluded rather than converted to zero; calendar disagreements,
  duplicate rows, incomplete balance components and sub-minor-unit input amounts refuse.
- Journal differences are eRev debit-minus-credit less legacy debit-minus-credit. Balance
  differences are eRev liability less asset/unbilled less legacy billed-minus-recognized.
  Fraction arithmetic preserves cents independently of Decimal context; no balancing plug.
- Separate section/currency totals and source-row contributor references are retained. Viewer
  sections, readable columns and the specified no-periods empty copy are implemented.
- Nine focused arithmetic/coverage checks and a frontend section check pass; type/lint checks pass.
  These use explicit source facts, not command-driven LMG-5 January/October acceptance evidence.
- Still required: independent legacy monthly-output reader preserving legacy rounding, authorized
  eRev journal/balance source selection, retained binding and worker registration/export journeys.
  RPT-42 remains unregistered; six catalogue builders remain. No readiness claim or deployment.


## Independent legacy monthly comparison inputs — October 19, 2026

- Implemented migration.parallel_legacy.snapshot over retained Contract_Live history. Gross
  journal construction follows component-major ordering, binary64 four-place rounding, the
  two-place zero filter, compensated grouped sums and final cents; no eRev engine output is used.
  Compatibility floating arithmetic is isolated from the exact comparison layer.
- Period-end contract balances sum latest obligation positions, never repeated contract totals.
  Coverage stops at the last source economic date. Entity mappings, duplicate identities,
  nonfinite amounts and unsupported currency/book selections refuse. Cross-entity contracts
  refuse rather than misattribute a legacy consolidated journal. Only two-decimal source currency
  is supported; the legacy format has no per-row currency column.
- Source identity includes raw-row digests, requested period boundaries and confirmed entity
  mapping. Journal/balance facts carry exact source-row references. Authorization and retained
  file/database integrity admission still belong to the upcoming report source reader.
- All ten archived monthly legacy gross exports (Jan–Oct 2023) match by account/debit/credit,
  preserving October's 5,043.84 debit / 5,043.85 credit imbalance. SQLite January Contract 2
  balance is -58.85. Focused checks: 17 passed; Ruff and Mypy pass.
- Remaining RPT-42 work: authorized eRev period/journal/balance selection, complete retained
  binding and report worker/export integration. Migration replay import remains unfinished
  (jobs.py explicitly refuses it); sandbox access must retain tenant/grant boundaries. These
  source checks do not complete LMG-4/5 or independent accounting acceptance.


## Authorized eRev parallel-run inputs — October 19, 2026

- Added parallel_actual.read: requires report.run for the requested entity IDs, resolves exact
  calendar boundaries, reads historical sealed journal facts through the existing legacy journal
  consolidation, and reads traced/frozen contract balances through the standard balance reader.
  It never switches tenant or implicitly authorizes a migration sandbox.
- Journal groups optionally retain composite line/partition/posting references. Their normal view
  behavior is unchanged when source capture is off. Actual facts retain period/currency, source
  version or frozen-lock/hash references, cutoff and a deterministic source-evidence digest.
- Missing expected contract balances withhold the period and record the missing population;
  unmatched currencies and calendar boundaries refuse. Missing actuals are never fabricated zeros.
- A real booking/computation/ledger case proves account totals match legacy_je_summary, repeat
  reads retain the same digest, missing population is excluded and report permission is required.
  Targeted PostgreSQL check: 1 passed; Ruff and Mypy pass. This is not LMG-5's complete migration
  acceptance or a cross-entity/locked-period browser journey.
- Still required: migration source-file/database admission, confirmed mapping retrieval, full
  retained binding/rebuild, worker/export integration and current grants at publication. Migration
  replay import and its sandbox lifecycle remain unfinished. Six builders remain unregistered.


## Migration source admission for parallel comparison — October 19, 2026

- Added parallel_sources.read_for_report. It binds the migration's original successful import
  operation, subject/parameters and cutoff; retrieves the confirmed entity mapping; and requires
  report permission for the complete mapped source population before opening plaintext.
- Verifies original LEGACY_DATABASE purpose, size and SHA-256 against the migration, then compares
  every retained history row's identity/raw hash with the original SQLite record. Temporary source
  copies and streams close on failure. Evidence retains file, operation, mapping and row identities.
- Linked sandboxes require their own authorized context; no tenant switch is performed. Current
  support is same-tenant complete-source admission, not partial-entity or replay-sandbox completion.
- Two real import scenarios pass (identity and renamed entity mappings), including incomplete-scope
  denial and a same-size altered-file digest refusal. The fixture now carries the actual source hash
  and job subject instead of placeholders. Ruff and new-module Mypy pass; checking the existing PG
  test module also reports five pre-existing type diagnostics outside this change.
- Next RPT-42 work: persist/rebuild the complete retained inputs, compose both readers with the
  comparison, register the worker and exports, and finish migration replay/sandbox lifecycle.
  Six catalogue builders remain unregistered; full LMG-4/5 accounting acceptance remains open.


## Retained parallel comparison inputs — October 19, 2026

- Added parallel_inputs.capture to compose authorized migration admission, independent legacy
  projection and historical eRev reading into a detached JSON input bundle. Period/currency
  selection remains explicit; current support requires the complete mapped entity scope.
- Saved inputs include both full snapshots, original source evidence, tenant/migration/entity
  scope and cutoff. Rebuild checks the server-bound digest, version, scope and source linkage,
  then recomputes the comparison without consulting mutable source tables.
- Targeted comparison suite: 10 passed, including JSON round-trip, changed amount digest refusal
  and changed entity scope refusal. New module passes Mypy; changed files pass Ruff.
- Still open: report parameter resolution, worker registration, persistence/export integration,
  current permission checks on publication and full migration replay/sandbox acceptance. The
  capture composition is type-checked but still needs a real database integration journey.
  Six catalogue builders remain unregistered; RPT-42 is not yet a completed user-facing report.


## Parallel comparison period and currency selection — October 19, 2026

- Source admission now verifies original import input-evidence hashes, requires full contract
  population coverage and derives the single reporting currency from captured contract inputs.
  Today's tenant currency cannot silently relabel a legacy source. Capture refuses other currencies.
- Added period resolution from the first period starting after cutover through the latest open
  period at known_at, using recorded state transitions. Explicit ranges may include closed periods;
  reversed or pre-cutover ranges refuse. Missing open periods produce empty coverage, not zeros.
- Connected defaults/ranges to parallel_inputs.capture and retained the requested period boundaries.
  Calendar resolution uses current definitions at capture; the resulting selection is retained.
- Targeted unit checks: 12 passed; three changed modules pass Mypy and changed files pass Ruff.
  Real import capture/rebuild checks cover identity and renamed mappings; dry-run imports correctly
  have no compared actuals. Worker registration, publication grants and export integration remain
  next, along with complete replay/sandbox lifecycle. Six catalogue builders remain unregistered.


## Parallel comparison worker and export integration — October 19, 2026

- Registered parallel_run_comparison and its retained-input source contract. Builder captures
  authorized sources, records exact cutoff/parameter selection and rebuilds from hash-verified
  retained facts. Changing entity, migration or period selection cannot reuse an unrelated binding.
- Worker reloads the original initiator's current report/export grants before building and output
  persistence. Source readers accept that verified principal with an explicit same-tenant check;
  no impersonation or implicit SYSTEM report grant is introduced.
- Real import -> CSV worker -> same-source rerun passes for identity and renamed entity mappings,
  with identical output hashes/control totals. Revoking permissions after queueing prevents file
  publication. These are empty comparisons because dry-run imports create no posted population.
- Targeted catalogue/source/parallel suites: 35 passed; changed production modules pass Mypy and
  Ruff. No schema change: the existing global definition already includes the output formats.
- Five catalogue builders remain unregistered: actual_vs_forecast, forecast_outputs,
  contract_sample_pack, period_evidence_pack and disclosure_pack. Populated RPT-42 worker/browser
  acceptance, XLSX/PDF journeys and migration replay/sandbox lifecycle remain unfinished.


## Disclosure workbook output foundation — October 19, 2026

- Added WorkbookSection and render_xlsx_pack: a contents worksheet identifies each section's
  source run/hash/status, followed by separately typed worksheets with their original source stamps,
  totals and tie-outs. Indexed names remain unique after Excel's 31-character truncation.
- Sections omitted under an election require a note and cannot carry rendered rows, totals or
  tie-outs. Their undisplayed source data must remain in retained evidence, outside the workbook.
- Shared the existing cell/grid writer with single-report exports, preserving numeric money,
  formula guards and disabled automatic URL conversion. Apostrophes at worksheet-name edges are
  sanitized. A seven-section workbook round-trip and existing single-report checks pass (4 checks);
  Ruff and Mypy pass for the changed output code.
- This is the output component, not a registered disclosure_pack builder. Child-run orchestration,
  frozen disclosure snapshot binding, seven-section assembly, PDF and viewer remain unfinished.
  Five catalogue builders remain unregistered. No new PR or deployment.


## Disclosure child report planning — October 19, 2026

- Added disclosure_plan.requests for the eight core reports plus contract_cost_rollforward
  required by section 6. Month-only plans contain nine children; quarter-to-date adds seven flow
  reports, using the entity's fiscal quarter. Closing balances and RPO reuse the period-end stock.
- Child selectors explicitly bind one entity, book, historical known_at and transaction currency
  view. Disaggregation requests revenue category/timing; waterfall preserves recognized/scheduled
  states. Every request passes the existing report parameter schema checks.
- Added queue through framework.create_run with a savepoint around the full plan. Returned child
  records retain section/basis, run/job IDs and the normalized parameter hash. The caller owns
  parent attachment, durable plan reuse and retry idempotency; this helper never commits.
- Two focused plan checks pass. A real database case verifies 16 scoped child runs and rollback
  on a later invalid child; Ruff and new-module Mypy pass.
- Remaining disclosure work: parent scheduling/child persistence, result verification/assembly,
  frozen snapshots, practical expedients, PDF and viewer. Nine live child inputs cover section 6
  in addition to the spec's older eight-core-child acceptance; full pack acceptance remains open.
  Five catalogue builders remain unregistered; no deployment.


## Durable disclosure parent-child attachment — October 19, 2026

- Added disclosure_children.ensure: locks the parent run, checks the initiating actor's current
  run/export permission, creates and attaches the complete child population in one transaction.
  Existing attachments are reused without fresh calendar resolution or replacement child runs.
- Reuse checks child identities/order, code/version, creator, entity/book/cutoff, output format,
  historical currency basis and matching period/quarter intervals. Missing, duplicated or mismatched
  children refuse. Locked parents explicitly require the separate frozen-disclosure source path.
- Real database check passes for 16 children, repeated calls and reuse after commit in a fresh
  transaction, plus permission denial and corrupted attachment refusal without new rows. Ruff and
  new-module Mypy pass. Concurrent callers serialize on the parent row; no concurrent stress test
  or completed pack publication is claimed.
- This helper is not yet wired to a registered parent builder/worker. Parent dependency waiting,
  child output verification and assembly, frozen snapshots, expedients, PDF and viewer remain open.
  Five catalogue builders remain unregistered; this does not complete RPS-15.


## Verified disclosure child results — October 19, 2026

- Added disclosure_results.collect: authorize/resolve attached children, return pending IDs
  without partial sections, refuse failed children, then verify the complete finished population.
  Reads original child JSON files under readable-file locks with bounded aggregate input size.
- Validates purpose/media type/size/file digest and run output hash, canonical report envelope,
  parameter binding, row count, control totals and tie-outs. Restores date/timestamp cells to typed
  ReportData; rejects duplicate row keys and envelopes that do not round-trip canonically.
- Real database journey now executes all 16 child report jobs and collects their verified outputs,
  after first observing pending children. This fixture has no booked accounting population; it
  validates task/output integration, not populated disclosure accounting acceptance. Three focused
  plan/decoder checks pass; Ruff and new-module Mypy pass.
- Remaining: registered parent worker/dependency scheduling, seven-section assembly, frozen
  disclosures, practical expedients, PDF and viewer. Five catalogue builders remain unregistered;
  no disclosure_pack completion or production-readiness claim.

## Practical expedient disclosure inputs — October 19, 2026

- Added disclosure_expedients.capture for the ten PRACTICAL_EXPEDIENT registry parameters.
  Requires current scoped report permission and an entity existing at the aware cutoff; resolves
  published entity/book policy values and retains their source IDs/levels, labels and references.
- ASC606 and IFRS15 references follow the local POLICIES table; forced IFRS exclusions are
  preserved. No website links are emitted. A nonpublic-only franchisor election on a public entity
  refuses rather than implying eligibility. These are entity policies, not contract-use assertions.
- POL-195 suppression hides rendered rows while retaining the full facts and omission note.
  Registry category/reference drift refuses rather than silently dropping a newly added expedient.
- Real registry reads verify ten ASC606 rows, the applied cost expedient with 340-40-25-4 and
  IFRS forced royalty exclusion; the existing 16-child database journey passes. Focused omission
  check passes; Ruff and Mypy pass for the new module.
- Still required: bind these facts to the parent's exact cutoff and frozen disclosure snapshots,
  assemble all seven sections, parent worker scheduling/publication, PDF and viewer. Policy test
  cutoff uses DB observation time separately from the child-run fixture; full pack acceptance
  is not implied. Five catalogue builders remain unregistered.

## Seven-section disclosure assembly — October 19, 2026

- Added disclosure_assembly.prepare/assemble: verifies complete attached child population and
  common tenant/entity/book/cutoff, captures entity policy facts at that exact cutoff, and groups
  verified child tables into all seven disclosure chapters with source run/hash references.
- Captures all nonpublic relief and interim policy values. Applies POL-192/193/196 at table level:
  balances remain while rollforward/other suppressed tables hide rows and totals. POL-195 hides
  the expedient table. Original child inputs remain available separately; interim-required chapter
  flags follow the resolved pack election. Disaggregation retains its existing timing-only handling.
- The database journey now assembles seven chapters after executing all 16 child tasks; fixture
  clock advances before parent creation so policy and child cutoffs match. It remains a no-booked-
  population journey, not full accounting acceptance. Two focused assembly/omission checks pass;
  Ruff and production-module Mypy pass.
- Still open: final side-by-side period/quarter presentation, chapter workbook/PDF and viewer
  integration, frozen disclosures and durable parent worker/dependency/publication lifecycle.
  Five catalogue builders remain unregistered. This assembly model is not a finished disclosure pack.

## Disclosure chapter workbook adapter — October 19, 2026

- Added render_xlsx_chapters with multiple independently typed/stamped tables per worksheet.
  Existing single-table exports reuse the same grid writer. Contents lists chapter/table status,
  source run/hash and worksheet; only the first table sets each chapter's frozen grid header.
- Added disclosure_workbook.render over the assembled seven chapters. Validates entity/book,
  policy hash and original child stamps/parameter hashes; re-encodes child data against its output
  hash and rejects changed displayed data. Omissions keep notes and no hidden source amounts.
- Database journey executes 16 child jobs, assembles the pack, generates a workbook and reopens
  it to verify Contents plus seven sheets and displayed source IDs/hashes. A mismatched displayed
  source stamp refuses. Three focused workbook/single-XLSX checks pass; Ruff and Mypy pass.
- Period and quarter-to-date are explicitly labelled separate tables at this stage. Required
  side-by-side presentation, PDF/viewer, frozen disclosures and parent worker publication remain
  open. The fixture has no booked accounting population; no full accounting acceptance claimed.
  Five catalogue builders remain unregistered; no deployment.

## Disclosure chapter PDF adapter — October 19, 2026

- Added PDF chapter export with an index whose page destinations follow actual pagination,
  original child stamps, per-table headings, repeated continuation grid headers, wrapped notes
  and parent-run page numbering. Tables start on separate pages; omitted amounts cannot render.
- XLSX/PDF reuse the same disclosure source/policy validation and chapter omission checks.
  Five focused PDF/workbook/single-report checks pass; production modules pass Ruff and Mypy.
- This is an internal export adapter, not end-to-end disclosure delivery. Parent scheduling and
  publication, frozen snapshots, viewer and side-by-side period/QTD layout remain outstanding.
  All five unregistered reports remain explicitly unfinished: disclosure_pack, actual_vs_forecast,
  forecast_outputs, contract_sample_pack and period_evidence_pack. No deployment.

## Disclosure dependency scheduling — October 19, 2026

- REPORT_RUN now uses a read-only readiness gate for disclosure parents. It checks the exact
  attached child population, scope/initiator, tenant/job/subject bindings and both job/report
  completion. Pending children defer delivery before taking an attempt; failed, cancelled,
  missing or inconsistent dependencies refuse instead of leaving the parent waiting indefinitely.
- Internal report insertion attaches disclosure children before transaction commit/dispatch.
  The public disclosure builder remains unregistered until rendering/publication and source
  binding are integrated; this change does not enable a partially implemented public report.
- Database journey covers a real parent delivery rescheduled at attempt 1 while remaining QUEUED,
  sixteen completed child jobs, readiness after completion and wrong-job/attachment refusal.
  Parent output persistence, retained reruns, frozen snapshots and viewer integration remain open.

## Disclosure parent artifact publication — October 19, 2026

- Added disclosure_execution to turn verified children/policies into a canonical seven-section
  JSON document, a table directory and original retained inputs. XLSX/PDF use the same verified
  chapter model. The parent hash identifies the canonical dataset; ordinary atomic report output
  storage, success audit and CTL-029/030 recording publish the result and binding together.
- Worker reloads the initiating user's current report/export grants, then assembles under that
  context. Original source inputs/policies stay in the binding; omitted rows/totals stay out of
  public sections. Aggregate child tie-outs include supporting inputs but expose only code/result,
  not suppressed source amounts. Rendering rejects unsupported formats and retained reruns.
- Real database journey now delivers the waiting parent again after 16 children finish, verifies
  job/report SUCCEEDED, reads the stored seven-section JSON and reconciles file/output hashes,
  counts and retained-input digest/cutoff. Ruff and production-module Mypy pass.
- Public registration remains closed: retained rerun reconstruction, frozen snapshots, viewer,
  side-by-side quarter layout and populated accounting acceptance are still required. The journey
  has no booked accounting population and currently publishes JSON; worker XLSX/PDF journeys
  remain to verify. Five catalogue builders remain unregistered. No deployment.

## Retained disclosure rerun reconstruction — October 19, 2026

- Added version-2 disclosure input codec retaining original child stamps alongside typed JSON
  inputs, identities, parameter/output hashes and policies. Rebuild validates scope, cutoff,
  version, digests, stamp/dataset agreement and full population, then executes section/election
  assembly again. It does not replay the saved parent output or resolve current child/policy data.
- Internal rerun insertion attaches original child IDs without queuing new children. Readiness
  validates retained inputs independently of current child job/file availability. Worker output
  rendering consumes the reconstructed pack and preserves original input evidence.
- The real parent/16-child journey now publishes a second parent with live capture forbidden;
  hashes, totals, tie-outs, child IDs and evidence match. Scope/digest corruption refuses. The
  newly retained stamp fields require evidence version 2; earlier internal version-1 captures
  refuse rather than silently adding current stamps. Ruff/Mypy pass.
- Public catalogue/API admission remains closed; frozen snapshots, viewer, quarter-column layout,
  export worker journeys and populated accounting acceptance remain open. Five catalogue builders
  are still unregistered. This internal rerun journey is not full disclosure completion.


## Draft disclosure public API admission — October 19, 2026

- Registered the composed disclosure worker separately from single-table BUILDERS. Creation
  and rerun use REGISTERED_REPORTS; its retained source contract is exposed through normal run
  metadata. There are 55 registered execution paths and four still-unregistered catalogue entries.
- Require one entity, ASC606/IFRS15 and explicit period. Initial attachment requires an open
  period at the source cutoff; missing/non-open/ambiguous state refuses. Explicit locked sources
  retain their existing no-frozen-dataset refusal. No live fallback for frozen requests.
- Converted the real 16-child/parent/rerun journey to HTTP creation and rerun, and verified run
  detail and JSON output download. Missing book/period and LEGACY requests return 422.
  The retained rerun still adds only one parent and reproduces hashes/totals with live capture
  forbidden. Source-contract/catalogue checks pass (23); Ruff/Mypy pass.
- User guide and release limitations describe the draft API and its boundaries. Frozen snapshots,
  chapter viewer, side-by-side quarter layout, export worker journeys and populated accounting
  acceptance remain open. This enables usable draft generation, not completed RPS-15/readiness.

## Disclosure chapter viewer — October 19, 2026

- Added seven-chapter disclosure view with expandable tables, period/QTD labels, interim flags,
  original source IDs/digests and omission notes. Only expanded, included tables load rows;
  amount columns identify shared currencies or carry companion currency columns when mixed.
- Report data now includes typed chapter/table metadata and optional section_table selection.
  Selected tables use normal pagination; cursor identity includes the table key. Unknown tables,
  duplicate selections and cross-table cursors refuse. Reads keep report permission/entity scope
  checks and verify the saved JSON digest before serving data. Ordinary directory reads remain.
- Real API journey verifies seven sections, ten expedient rows, pagination and wrong-table cursor
  refusal. Component check verifies lazy loading and omitted-table suppression. Ruff/Mypy,
  frontend TypeScript and targeted ESLint pass; OpenAPI/client types regenerated.
- Full browser/accessibility acceptance, frozen snapshots, quarter side-by-side layout, populated
  accounting acceptance and remaining export worker journeys remain open. No deployment.

## Quarterly disclosure comparison summaries — October 19, 2026

- Added semantic period/QTD comparison for the six displayed flow reports. Row identities use
  section/contract/obligation/dimension/line codes and currency instead of source row positions or
  conditional currency suffixes. Different labels receive separate columns; missing population
  stays blank with presence flags. Duplicate identities or schema/election mismatch refuse.
- Disaggregation uses each source's existing range total, excluding its varying monthly buckets.
  No money is summed or rounded. Comparison summaries precede original source tables in JSON,
  workbook and PDF chapters; canonical parent hashes include comparison output. Summary digests
  identify their dataset and notes retain both original source run/hash references.
- The viewer labels combined-basis tables and their comparison digest separately from policies.
  Two populated alignment checks pass. The real 16-child/API/parent/rerun journey verifies six
  summaries, their hashes and workbook period/QTD headers; same-source rerun remains identical.
  Ruff/Mypy and frontend type/lint/component checks pass.
- Full populated accounting acceptance, PDF wide-table readability, browser acceptance, frozen
  snapshots and remaining export worker journeys remain open. No deployment or readiness claim.

## Immutable draft disclosure snapshots — October 19, 2026

- Added disclosure_snapshots.write_draft: locks the running parent and saves all seven E-65
  kinds with entity/book/period/cutoff, original per-section child inputs/stamps, policies and
  supporting source digests. Suppression affects published tables, not retained snapshot inputs.
- The normal worker attaches snapshot IDs in the same transaction as report output, source
  binding and SUCCEEDED. Repeated writes reuse a complete identical set; duplicate/partial,
  mismatched or unavailable attachments refuse. Drafts explicitly have no period_lock_id.
- Real API/16-child/parent/rebuild journey now verifies seven rows per parent, hashes and
  attachments, repeated-writer reuse, and new rerun IDs with identical per-kind data hashes.
  Ruff and production-module Mypy pass. Snapshot rows use the existing append-only table.
- Lock-time capture remains incomplete: current E-64 files cannot alone supply opening-liability
  revenue and policy facts. The lock job must capture these at its exact cutoff and atomically
  publish genuinely locked disclosures; drafts must never be promoted/relabeled as locked.
  Snapshot read APIs and as-locked parent integration also remain open. No deployment.

## Disclosure snapshot read APIs — October 19, 2026

- Added API-R-42 disclosure snapshot list/detail with report.run authorization, entity/book/
  period/kind/source-report filters and keyset pagination. Metadata lists avoid loading dataset
  JSON; detail verifies digest, schema and snapshot/parent scope. Both return no-store responses.
- Reads require a successful disclosure parent, actual snapshot attachment, matching entity,
  book, period/calendar and lock identity, plus the parent's complete report permission scope.
  Missing/out-of-scope records return 404; unpublished or unattached rows stay out of counts/pages.
- Real API journey verifies seven draft records, filtering, count, disjoint pagination, detail
  digest and explicit draft classification. An empty report permission scope yields no rows and
  refuses detail. Ruff/Mypy pass; OpenAPI and generated frontend types updated.
- Lock-time capture/as-locked execution, snapshot register UI and full accounting acceptance remain
  open. Existing draft evidence is not relabelled as locked. No deployment.

## Read-only lock disclosure capture — October 19, 2026

- Added disclosure_freeze.capture over the existing SnapshotScope and one read-only SYSTEM
  reader. It executes the nine period/seven quarter source producers, normalizes parameters,
  fixes historical cutoff, preserves typed canonical datasets and their input bindings, and
  captures practical-expedient/nonpublic/interim policy facts at the same instant.
- Enforces entity-calendar membership, accounting book, aware/equal freeze cutoff, schema,
  unique row identities and bounded retained payload size. Does not enqueue jobs or invent
  report/job IDs. Policies expose a separate lock-only entry requiring SYSTEM plus a read-only
  transaction; ordinary SYSTEM calls still fail the existing report permission gate.
- Real database journey captures sixteen inputs under freeze.system_unit and compares every
  dataset against ordinary child jobs at the same cutoff; no report count change. Caller
  context and ordinary SYSTEM policy access refuse. Ruff/Mypy pass. Fixture has no booked
  accounting population, so independent accounting correctness is not implied.
- The collector is not yet invoked by lock approval: atomic persistence of genuine source report
  identities/seven locked snapshots and as-locked parent rendering remain to integrate. Existing
  draft snapshots stay drafts. No lock support, deployment or production-readiness claim.

## Disclosure snapshot viewer — October 19, 2026

- Disclosure report pages now expose a saved-snapshot panel: lazy paginated metadata,
  seven named kinds, explicit draft/locked classification, entity/book/period and individual
  verified detail reads. Expanded records show cutoff, reporting basis, snapshot ID and digest;
  verification failures offer retry without claiming successful validation.
- Retained suppressed source amounts are not rendered in this panel. Original disclosure
  tables continue to apply their elections. No new export permission or raw-data download.
- Three focused component checks cover lazy loading, failure/retry and retained-input hiding;
  TypeScript and targeted ESLint checked. Full browser acceptance remains open.
- This is a per-report viewer, not a cross-report snapshot register. Lock approval persistence
  and as-locked execution still remain open; no deployment or readiness claim.

## Atomic disclosure publication at lock — October 19, 2026

- ASC606/IFRS15 lock approval now captures sixteen period/QTD inputs and policies through the
  shared read-only SYSTEM reader, then publishes actual synchronous source reports, a seven-
  chapter JSON disclosure parent and seven immutable snapshots within the lock transaction.
  Source reports have null jobs, normal historical source bindings and actual output files;
  the parent/snapshots alone claim the period lock. CTL-029/030 and audit evidence are recorded.
- Validates lock/entity/calendar/book/cutoff, child plan/selectors, policy and dataset hashes,
  source bindings and row identities. Uses UoW savepoints so failed publication drops records,
  audit buffers and hooks. Repeated publication of an existing lock refuses. The seventh
  snapshot also retains supporting waterfall inputs for later frozen reconstruction.
- Existing twelve E-64 datasets keep their formats. Scope readers admit boolean quarter only
  for disclosure parents; the report viewer distinguishes saved lock evidence from drafts.
  The existing API serves the stored JSON chapters and seven scoped verified snapshots.
- Targeted database journeys cover draft/rerun, late-child failure rollback, genuine source
  identities, snapshot/parent HTTP reads, duplicate refusal and actual close approval capture.
  Production Python typing/lint and frontend component/type checks pass. Independent accounting
  acceptance, full browser/release checks and performance verification remain open.
- Next: admission/rebuild from saved lock snapshots, locked XLSX/PDF exports and rerun; no
  historical-lock backfill or current-data fallback. Other reporting/system backlog remains.
  No deployment, new PR or production-readiness claim.

## Frozen disclosure execution and exports — October 19, 2026

- Added a verified E-65 reader: complete seven-kind population, single synchronous origin,
  immutable attachment/scope/cutoff, payload hashes, typed child data/stamps and reconstructed
  document equality. All original inputs, including supporting waterfalls, come from snapshots.
- Ordinary report creation and rerun now admit lock-backed disclosure packs, deriving the exact
  lock cutoff and checking explicit selectors. Period-only uses nine inputs, quarter uses sixteen.
  The normal worker renders JSON/XLSX/PDF with current requester permissions. Existing frozen
  inputs are reused; no source jobs, new snapshots, child file reads or live-policy fallback.
- Snapshot listing follows attachments for derived exports. Closed-period report views default
  to frozen disclosures and saved quarter inputs, without forwarding an unrelated global timestamp.
  Locks without complete E-65 evidence refuse rather than reconstructing past disclosures today.
- Real database/API/worker journey passes all formats, matching original quarterly JSON digest,
  same-source rerun, monthly selection and unchanged snapshot count. Python lint/type checks
  and focused frontend parameter/type/lint checks pass. PDF byte-format verification is not
  visual acceptance: wide tables, full browser/accounting validation and release checks remain.
- RPS-15 remains open; other missing reports and system work remain. No deployment or readiness
  claim; changes published directly on main.

## Readable wide disclosure PDFs — October 19, 2026

- Replaced chapter-table ellipsis clipping with wrapped cells and horizontal column groups.
  Repeats row ordinals/identifying context and headers, keeps currencies beside amounts, and
  groups adjacent period/QTD measures where they fit. Ordinary rows stay together; long rows
  continue under the same ordinal. Very long labels get full-text legends, not clipped headers.
- Wrapped chapter stamps/notes and corrected contents offsets against final pagination.
  Added table header rules and compact currency headings. Omitted sections remain amount-free.
  Existing single-table PDF layout and canonical JSON accounting dataset hashes are unchanged.
- Six focused checks pass, including large negatives, mixed currency, long IDs, oversize
  narratives/labels, page/column geometry and legacy footer behavior; Ruff/Mypy pass. Rendered
  and inspected all five pages of a synthetic wide disclosure PDF with the PDF skill workflow.
- This verifies the layout sample, not accounting acceptance. The current standard-font
  WinAnsi limitation, broad browser/release checks and independent accounting sign-off remain.
  Four unregistered report families and the other system backlog still need development.
  No deployment; publish directly to main.

## Forecast manual event capture — October 19, 2026

- Added explicit `forecast_event_set_id` on the contract event append API. Registered scenario
  drafts apply facts under BR-FC-02 and retain ordered method/path/body inputs atomically.
  Requires tenant-wide scenario.use plus the ordinary contract event permission and validation.
- Publication and command capture share the input-set lock; published versions reject new
  events. A capture failure rolls back facts, computations and buffered audit work. Existing
  ordinary event approval behavior remains the default when no input set is selected.
- Real snapshot-to-scenario/API journey passes manual progress capture, same-key retry,
  failed-capture rollback and published-set rejection. Two production approval/evidence checks
  also pass. Ruff/Mypy and OpenAPI generation pass.
- Updated API schema/client types and user guide. Import association, ordered refresh/replay,
  forecast jobs, forecast outputs and actual-vs-forecast remain unimplemented; FCS-2 stays open.
  Contract sample and period evidence packs also remain outstanding. No deployment.

## Forecast file input pipeline — October 19, 2026

- Revision 0181 adds an immutable tenant-scoped import-to-input-set binding, exposed in import
  reads. Scenario drafts accept progress, usage, cost and invoice fact files through existing
  validation/diff/commit stages. Other import workflows retain their normal approval path.
- Ready forecast files submit under BR-FC-02 without an approval request. The worker rechecks
  the uploader's current scenario grant/token scope and underlying template write scope, locks
  diff contract bases before applying, and atomically appends successful upload IDs to the set.
- Input-set publication refuses pending files; invalid/failed files add no inputs. Captures and
  publication share a lock. CTL-044 records the scenario approval exemption as not applicable.
- Real scenario/API/worker journey passes file commit, no approval request, pending-publication
  refusal and over-delivery rejection. Two ordinary import regression checks and the forecast
  schema upgrade/downgrade check pass; Ruff/Mypy and OpenAPI generation pass.
- Updated API/client types, snapshot handling, data model and user guide. Scenario refresh and
  ordered replay still need implementation, followed by forecast execution and both forecast
  reports. Evidence-pack reports also remain open. No deployment or production-readiness claim.

## Forecast input application order — October 19, 2026

- Revision 0182 records one sequence across API commands and successful file commits. Both
  capture paths append the sequence under the input-set lock, in the same transaction as facts.
  Publication validates complete, unique coverage and per-source order, then hashes the sequence.
  New versions preserve the sequence alongside their copied command/file inputs.
- Historical populated sets without sequence evidence remain readable but cannot be extended
  or replayed by guessing an order. Empty historical sets can initialize a verified empty order.
- Mixed API/file/API capture, published order and version copying pass the real scenario journey;
  five malformed/legacy order checks and the schema upgrade/downgrade check pass. Python lint,
  type checking and OpenAPI generation pass.
- This supplies a required input for deterministic refresh/replay; the refresh orchestration,
  forecast computation, forecast reports and evidence-pack reports remain unfinished.
  No deployment or production-readiness claim.

## Published forecast replay inputs — October 19, 2026

- Added the source reader for refresh: verified publication hash, complete input order and
  published version ancestry; inherited file inputs must belong to that chain and be committed.
  The reader checks the current requester's scenario and underlying event/import permissions.
- Retains original file/evidence bytes with size/hash verification and a combined size limit;
  keeps the committed template version, parameters, quarantine setting and verified mapping
  definition. Only captured contract-event POST commands are admitted, never arbitrary URLs.
  Publication and reading share the same canonical content definition.
- The mixed-input scenario journey verifies inherited source-file materialization, ordered event
  bodies, publication/file corruption rejection and permission refusal; Ruff/Mypy pass.
  Refresh orchestration, applying
  these inputs in a new copy and switching the scenario are still unfinished. Forecast outputs,
  actual-vs-forecast and evidence packs also remain open. No deployment/readiness claim.

## Transactional forecast file replay — October 19, 2026

- Added an internal replay executor that creates, validates, previews, submits, commits and
  computes one forecast file in the caller's transaction. No asynchronous stage/compute jobs
  can overtake the next input. Retained quarantine behavior is explicit; normal import routes
  retain their asynchronous execution and approval rules.
- Failed stages roll back facts, captured input order and audit buffers. Existing template,
  draft-set, uploader and contract permissions remain enforced. The scenario journey covers
  successful replay without queued jobs and invalid-input rollback; ordinary import coverage
  is retained. Targeted checks and Ruff/Mypy pass.
- This is an internal building block, not a finished refresh endpoint. Resource copying,
  command replay, durable refresh orchestration and atomic scenario replacement remain open.
  Forecast outputs, actual-vs-forecast and both evidence packs remain reporting priorities.

## Transactional forecast command replay — October 19, 2026

- Added the internal command executor alongside file replay. Commands authorize and lock the
  current contract in the target copy, apply retained payload/evidence through the normal event
  path and capture the input only after synchronous computation succeeds. Large groups do not
  enqueue deferred work that could overtake subsequent inputs. Ordinary HTTP behavior is unchanged.
- Computation failure rolls back the event, computation, input capture and audit buffers. The
  real scenario journey exercises failure after computation, subsequent successful replay and
  mixed file/command order without new jobs. Targeted checks and Ruff/Mypy pass.
- Resource materialization, durable refresh orchestration, scenario replacement and the forecast
  report builders remain unfinished. No deployment or production-readiness claim.

## Forecast replay file materialization — October 19, 2026

- Added target file materialization from the authorized published-input bundle. It checks the
  exact file manifest, bounded bytes and retained hashes, and requires a draft of the same
  logical scenario plus tenant-wide scenario permission. Copying uses the normal authorized
  upload path with content checks, encryption, deduplication, uploader access and audit.
- Returns target file bindings and rewritten command evidence/import source references without
  mutating the source bundle. Mapping descriptors remain retained for separate resolution.
  The scenario journey checks deduplication, evidence rebinding/readback and corrupt/missing
  file refusal; targeted verification and Ruff/Mypy pass.
- Mapping-profile resolution, persisted refresh orchestration, final scenario switch and
  forecast report builders remain open. No deployment or production-readiness claim.

## Retained forecast import mappings — October 19, 2026

- Revision 0183 retains a forecast replay import's verified original mapping as immutable JSON,
  separate from published target configuration. Internal replay validates its hash/template and
  persists it; ordinary import APIs cannot supply this snapshot and retain publication rules.
- Validation and header preview consume the retained aliases/constants. Published-input reading
  preserves the same mapping for subsequent refreshes, including when the source profile is
  absent or superseded in the new copy. Upload audit identifies its original profile and hash.
- The scenario journey imports an alias column without a target profile, computes successfully,
  then publishes and reads back the retained mapping; ordinary customer import also passes.
  Static checks and forecast schema upgrade/downgrade pass. Snapshot inventory clears this
  operational field with the source forecast binding.
- Durable refresh request/orchestration, scenario replacement and forecast report builders remain
  unfinished. No deployment or production-readiness claim.

## Atomic ordered forecast replay — October 19, 2026

- Connected file materialization, retained mapping consumption and command/file execution into
  one ordered replay operation for an empty target draft. It publishes only after every input
  computes successfully and records source/target publication hashes plus upload bindings.
- The caller owns the transaction; any failure or heartbeat cancellation rolls back the whole
  bundle, including earlier inputs and staged file metadata/audit. The input set cannot be
  replayed twice after publication. No child computation jobs can overtake the sequence.
- The real scenario fixture exercises command → mapped file → command, cancellation after
  the file with complete rollback, successful retry/publication and duplicate refusal.
  Targeted scenario verification, Ruff and source-module Mypy pass.
- Durable refresh job state, fresh-copy lifecycle and atomic scenario replacement still need
  integration. Forecast report outputs and actual-vs-forecast remain unfinished; no deployment.

## Held forecast copy and activation gate — October 19, 2026

- Snapshot loading can now retain SUSPENDED after successful copy/verification when its internal
  caller requests deferred activation for the scenario requester. The load summary records this
  explicitly; ordinary loads still activate immediately.
- Added an internal activation gate for the completion transaction: the expected held snapshot
  must have completed, period replay must permit point-in-time use, the registered scenario's
  expected input publication/hash must match, and the current requester must hold scenario.use.
  The gate updates status and audit without committing or changing the source scenario itself.
- The scenario journey verifies real deferred loading, refusal to open the suspended workspace,
  draft/hash refusals and successful activation. Ordinary scenario creation also passes;
  targeted checks and Ruff/Mypy pass.
- Persisted refresh orchestration, failure recovery and source scenario replacement remain
  unconnected; forecast reporting is still unfinished. No deployment/readiness claim.

## Durable scenario refresh reservation — October 19, 2026

- Revision 0184 adds production-scoped refresh records with immutable source/target tenants,
  selected input/hash, snapshot and job identities. Partial uniqueness admits one queued/running
  refresh per scenario; transition guards freeze terminal evidence and set-once result fields.
- Internal admission serializes on the source scenario, verifies the selected published inputs
  and the requester's queued copy job, and records the reservation. Start/failure transitions
  retain lifecycle audit. Archived or replaced source scenarios cannot start refresh execution.
- A running reservation now associates a held target with its original logical scenario for
  input replay; source pointer replacement is not needed to prepare the new inputs. Archiving
  refuses pending refreshes. Refresh records are operational, excluded from snapshot copying.
- The scenario journey verifies reservation, duplicate refusal, archive protection, repeat start,
  failure and immutable fields. Schema/transition/RLS round-trip and Ruff/Mypy checks pass.
- The request endpoint, worker integration, terminal cleanup and atomic source switch remain
  unfinished. Forecast outputs/actual-vs-forecast still remain open; no deployment/readiness claim.

## Scenario refresh API, worker and atomic switch — October 19, 2026

- Added POST /scenarios/{id}/refresh with source row precondition, published input selection,
  idempotency and atomic snapshot-job/reservation creation. OpenAPI/client types regenerated.
- Reserved snapshot jobs now reauthorize the requester, read the selected publication, export
  current production, load a held copy and replay the ordered inputs. Completed held copies can
  be reused; an already-completed refresh returns its retained result. Partial copy failures
  settle the refresh and archive the incomplete target while keeping the old scenario usable.
- Publication, target activation, old-copy archive, source pointer/base/last-refreshed update,
  refresh result and three-workspace audit commit together. Retired old-copy worker writes are
  refused even after their source pointer moves. Cancellation settles queued reservations and
  cannot undo an already-completed switch.
- Real API/worker checks cover failed completion with old-copy preservation, a subsequent
  successful refresh, mixed mapped-file/event replay, idempotent HTTP retry, old-write refusal
  and queued cancellation. Ordinary scenario creation also passes; Ruff/Mypy/OpenAPI pass.
- Refresh UI, broader concurrency/crash recovery and specified accounting acceptance remain
  open. Forecast output and actual-vs-forecast report builders remain unfinished. No deployment.

## Forecast output section projections — October 19, 2026

- Added RPT-39 table projections for billing by contract/horizon period, projected balances
  by entity/currency/period end, and journal preview by period/account role/currency.
- Billing consumes effective net document contributions (void/credit handling stays in the
  existing billing reader), preserves signed credits and excludes dates outside the horizon.
  Balance stocks remain separate by end date and skip input TOTAL rows to avoid double counting.
  Journal preview retains gross debit/credit activity, including reversals, from signed sealed
  ledger inputs; it does not create journal batches. Every total is currency-specific.
- Three focused checks cover credit amounts, USD/JPY precision, multiple period-end stocks,
  reversals and stored functional-currency amounts. Ruff/Mypy pass.
- These are data projections, not a registered/completed forecast report. Five-section assembly,
  source capture, forecast-run execution, retained report exports and UI remain open. Journal
  reporting-currency valuation still needs its governed source adapter; no parity conversion is
  assumed. Forecast and actual-vs-forecast remain unfinished. No deployment/readiness claim.


## Forecast output source capture and five-section assembly — October 19, 2026

- Connected the internal RPT-39 assembly to the existing revenue waterfall, net billing,
  period-end balance, RPO and sealed-subledger readers. All reads share an exact cutoff,
  book and authorized entity scope. Each child keeps independent source evidence; multiple
  balance-period reads cannot overwrite one another. Same-source reruns remain open.
- Billing uses each entity's own calendar boundaries; balance stocks are grouped by actual
  end date. Horizons must be consecutive in every selected calendar. Functional billing uses
  the governed spot-rate adapter; unsupported report-currency conversion is refused.
- The five tables omit report tie-outs; projected RPO includes section 1 only and preserves
  underlying election controls. Journal preview creates no posting or journal batch.
- Real computed scenario capture passes within the existing replay/refresh journey; four
  focused projection checks and Ruff/Mypy pass. No full-suite run or deployment.
- Still unfinished: forecast-run API/worker, durable report publication and exports, chart/UI,
  actual-vs-forecast, contract sample pack and period evidence pack. This internal assembly
  is not yet a registered report and does not establish production readiness.

## Forecast output download rendering — October 19, 2026

- Added internal RPT-39 JSON, XLSX and CSV rendering from the captured five-section dataset.
  XLSX uses the established workbook renderer with a contents page, five typed tables and
  run metadata. CSV is a deterministic ZIP of five separate schemas plus a manifest with
  each file's hash, byte count, controls and run stamp. JSON preserves section boundaries.
- Exports carry scenario, input publication/version/hash, horizon and source cutoff. The
  dataset hash accompanies XLSX/CSV output. Raw source evidence is not exposed. Scope,
  missing sections, unsupported PDF and output-format visibility changes are refused;
  format changes require a new capture so RPO election visibility is preserved.
- Targeted renderer checks cover metadata, signed numeric money, safe literal contract text,
  CSV file hashes and refusals. Real scenario capture-to-JSON and Ruff/Mypy also pass.
  Durable report publication/download routes, forecast execution,
  charts/UI, actual-vs-forecast and both evidence packs remain unfinished. No deployment.

## Forecast report data API and viewer — October 19, 2026

- Aligned forecast JSON with the existing report-data chapter/table envelope, including a
  five-row section index, typed table datasets and per-table hashes. Added typed forecast
  header metadata to GET report-runs/{id}/data; existing chapter pagination can serve each
  forecast table independently and rejects cursors reused across the index and a table.
- Added the forecast viewer branch with saved scenario/publication, horizon and cutoff,
  expandable tables, currency-aware columns and retry/empty states. Reused the disclosure
  table renderer without its policy/snapshot controls. CSV download filenames now use .zip
  for forecast outputs, matching the archive format.
- Four targeted backend checks, forecast/disclosure component checks, Ruff/Mypy, ESLint,
  TypeScript and OpenAPI generation pass. No deployment or full-suite run.
- Run admission/computation, durable report publication and end-to-end creation remain open;
  the report is still unregistered. The viewer requires a saved forecast report and does not
  yet make one available through the UI. Revenue chart, actual-vs-forecast and both evidence
  packs remain unfinished. Production readiness and independent accounting acceptance remain open.

## Atomic forecast report publication — October 19, 2026

- Added an internal publisher for a running forecast: verifies its published input identity/hash,
  current scenario and requested entity/book/horizon scope, then stores an ordinary report run,
  encrypted output and CTL-029/CTL-030/audit evidence in the caller's transaction. Reports are
  attached to the parent forecast. Duplicate formats are refused under the parent row lock.
- JSON, XLSX and CSV publication preserve the captured currency view, output visibility basis,
  cutoff, engine release, actual scenario name and tenant negative-number style. CSV also saves
  its manifest for the normal manifest download route. Independent child source evidence is
  retained internally; computation reruns remain explicitly open rather than claiming a rebuild.
- The real scenario journey verifies rollback after file storage, successful publication,
  duplicate refusal, three-format persistence, saved JSON API reading and CSV/manifest downloads.
  Targeted source/export checks and Ruff/Mypy pass. Public admission/computation orchestration
  is still missing; this is an internal transaction primitive, not a completed forecast workflow.
  Revenue chart, actual-vs-forecast, evidence packs and accounting acceptance remain open.


## Forecast-run API and worker — October 19, 2026

- Added POST/GET/list forecast-runs in scenario workspaces, with idempotent admission,
  published-input hash verification, scoped report/export permissions and consecutive horizon
  validation. Requested formats default to JSON; callers may select XLSX/CSV too.
- Registered FORECAST_RUN: reloads the active requester, validates the queued input/state hash,
  recomputes activated scenario groups and publishes all selected five-section reports with
  the parent success transition in one transaction. It does not reapply already-applied inputs.
  Cancellation checkpoints roll back partial work; the final job-row check serializes cancellation
  with publication. Queued cancellation/failure settles the parent and completed publication
  cannot be cancelled. Revision 0185 admits forecast_run as the durable job subject.
- Real API/worker verification covers idempotency, three reports, production refusal, listing,
  completed-cancel refusal, queued cancellation and computation failure without partial reports.
  OpenAPI/client schemas and the user guide now describe the runnable API.
- FCS-3 remains open: K-11 specified accounting acceptance, broader concurrency/crash coverage,
  creation screens, revenue chart, general report-catalogue execution and same-source reruns
  are still unfinished. Actual-vs-forecast and evidence packs remain priorities. No deployment.

## Forecast run creation and history screen — October 19, 2026

- Added `/reports/forecasts` with published-input selection, scoped entities, consecutive
  calendar horizon, transaction/functional currency and JSON/XLSX/CSV output choices.
- Connected idempotent submission, job progress/cancellation, paginated run history, saved
  report links and JSON table previews. Errors and missing permissions are visible; production
  workspaces cannot create forecasts. Three focused UI checks cover submission and access.
- Scenario creation/refresh and input editing UI remain open, along with forecast revenue
  chart, actual-vs-forecast, contract sample pack and period evidence pack. No deployment.

## Actual-vs-forecast comparison projection — October 19, 2026

- Implemented contract/category revenue comparisons, saved-horizon validation, entity scope,
  signed variance and percentage, zero-forecast null percentage and separate currency totals.
  No-actuals output differs from zero-net production postings; no currency conversion is inferred.
- Four focused checks cover population union, credit signs, currencies, zero bases, no actuals,
  category aggregation, period/entity selection and invalid numeric inputs. Ruff/Mypy pass.
- FCS-4 remains unavailable until production actuals are captured at refresh before scenario
  replay, old forecast records can be resolved across refreshes, and the retained builder and
  UI are connected. Current scenario recomputation must not be mistaken for posted actuals.

## Forecast lookup across scenario refreshes — October 19, 2026

- Added an internal saved-forecast resolver from the active scenario through successful refresh
  predecessors. Failed/disconnected copies are excluded; ambiguous or cyclic lineage is refused.
  Saved runs must be succeeded and belong to a published input set of the same logical scenario.
- Current requester entity permissions are checked again. Tenant SQL context is restored on
  both successful reads and refusals. The result separates production snapshot cutoff from
  refresh completion time, for the eventual posted-actual reader and report header.
- The real scenario/refresh journey passes archived-run resolution, missing-run refusal,
  permission removal and context restoration; three lineage checks and Ruff/Mypy pass.
- Actual-vs-forecast remains unfinished: posted-actual capture, archived output retrieval,
  retained-source report builder, catalogue registration and UI still need connection.


## Retained forecast data and archived revenue reading — October 19, 2026

- Forecast publication now retains encrypted canonical JSON for XLSX/CSV runs as well; JSON
  reuses its existing output file. The dataset reference is saved with the source binding in
  the same publication transaction, so later comparison does not recalculate the original forecast.
- Added an internal reader through the authorized scenario history resolver. It checks the
  saved output hash, scenario/input/parent identities, book/currency/entity/horizon scope and
  revenue-table hash, returning only revenue. Legacy JSON remains readable; old file-only
  outputs without retained data are explicitly refused. Tenant context is restored on exit.
- The real scenario journey passes all three retained formats and archived revenue reading
  after refresh. Ruff/Mypy pass. Production actuals, comparison builder/registration and UI
  remain open; no generic archived-download access or production-readiness claim is added.


## Snapshot-cutoff production actuals reader — October 19, 2026

- Confirmed SBX-03 snapshots deliberately omit journals. Added a separate production-only
  actuals reader using the journal extract's cutoff-bound lifecycle evidence and current entity
  permissions. It retains acknowledged revenue batches only, preserving transaction/functional
  debits and credits and journal/contract/obligation identities for the comparison mapper.
- Later acknowledgements/cancellations are evaluated at the snapshot cutoff; cancelled lines,
  duplicate lines, out-of-scope books/entities and post-cutoff lines are excluded or refused.
  Scenario journals cannot be passed off as production actuals.
- Six focused checks and the real scenario journey pass, including empty production actuals
  despite scenario computations and refusal of a sandbox source. Ruff/Mypy pass.
- Still required: durable capture retention in creation/refresh, category/contract mapping,
  comparison builder/registration and UI. FCS-4 is not yet runnable. No deployment.


## Durable actuals capture in creation and refresh — October 19, 2026

- Revision 0186 adds immutable, tenant-scoped forecast_actuals_capture records, unique per
  source snapshot and linked to encrypted SNAPSHOT_DATASET files. Both ASC606/IFRS15 retain
  their own cutoff, entity scope and acknowledged revenue lines. Downgrade refuses evidence loss.
- Scenario creation and refresh workers retain actuals before snapshot completion/replay under
  the requester's current production permissions. Snapshot-row locking serializes retries;
  existing captures are reused. Completed legacy snapshots cannot acquire a later baseline.
  Journals still are not copied into sandboxes; failed-refresh capture evidence is preserved.
- The real creation/refresh journey passes migration, both-book file digest/content checks and
  immutable-update refusal. Ruff/Mypy pass. Source actuals require report.run for every captured
  source entity; no scope is silently omitted.
- Still open: authorized retained-actuals reader, contract/category mapping, comparison report
  builder/registration and UI. No deployment or overall production-readiness claim.


## Authorized retained-actuals reading — October 19, 2026

- The scenario history result now identifies the exact current actuals snapshot. Added an
  internal actuals reader that reauthorizes the current scenario and historical forecast,
  verifies the snapshot target/status/cutoff and encrypted file digest, and checks retained
  book/entity/cutoff metadata before returning only forecast-scope rows.
- Other books, entities and periods never leave the reader. Duplicated, cancelled, late or
  out-of-capture rows are refused. Missing legacy capture is explicit; no live-source fallback.
  Production SQL context is restored on exit, including errors and revoked permissions.
- Six focused scope/integrity checks pass. The real refreshed-scenario journey reads its
  retained empty actuals and denies access after permission removal. Ruff/Mypy pass.
- Remaining FCS-4 work: contract/category dimension mapping, comparison report builder and
  registration, screen connection and populated accounting acceptance. No deployment.


## Saved forecast dimension mapping — October 19, 2026

- Forecast revenue exports now retain the original revenue category. The archived reader
  validates the saved scope-evidence hash and resolves entity IDs from the retained entity
  configuration, not current names or inferred ordering.
- Added the forecast-side comparison mapper: expands obligation rows over the saved horizon,
  preserves period money signs/currencies, excludes totals and refuses duplicate/incomplete
  rows. Legacy data without category still supports contract mapping but refuses category use.
  Nullable categories remain separate from a literal category named Unassigned.
- Ten focused mapper/comparison checks and the real archived-forecast refresh journey pass;
  Ruff/Mypy pass. Actual-side dimension mapping, report builder/registration and UI still
  remain. FCS-4 is not yet runnable; no deployment.


## Actual dimensions and comparison assembly — October 19, 2026

- Actuals capture now freezes immutable contract external IDs and category availability. A
  single obligation/product history and a product unchanged since the cutoff establish the
  category; changed/ambiguous/missing history stays explicitly unknown rather than becoming
  Unassigned. Contract mapping still works when only category history is unavailable.
- Added actual-line projection using saved transaction/functional credit minus debit. Connected
  both authorized retained-source readers to the comparison projector, with refresh-race checks
  and pre-aggregation fact/digest evidence for the forthcoming report-framework adapter.
- Seven focused dimension checks pass. The real scenario journey verifies populated obligation
  label lookup, historical absence and archived forecast plus empty actuals comparison. Ruff/
  Mypy pass. Populated production-posting accounting acceptance is still outstanding.
- Report-framework registration, same-source rebuilding and UI remain open; the internal
  comparison path is implemented but the public report is not yet runnable. No deployment.

## Actual-vs-forecast standard report execution — October 19, 2026

- Registered actual_vs_forecast in the standard report framework (56 registered definitions,
  including disclosure; 55 ordinary builders). Workers reload current scenario/report access.
  Live builds use the requesting user for authorized source reads and restore worker context.
- Added retained-fact rebuilding with digest, tenant/run/entity/book/currency/selection and
  cutoff checks. It recomputes variances from original facts without live-source reads or saved
  output replay. Revision 0187 updates report IPE to the real retained snapshot/file sources.
- The real scenario journey creates a standard REPORT_RUN, executes it to SUCCEEDED JSON and
  rebuilds the same empty-actuals result with live reads forbidden. Migration and 17 focused
  source-contract/rebuild checks pass; Ruff/Mypy pass.
- Dedicated UI selection, all file-format verification and populated accounting acceptance
  remain. FCS-4 is now registered/runnable, but its acceptance is not complete. No deployment.

## Actual-vs-forecast selection and report screen flow — October 19, 2026

- Added the SF-17 comparison form: saved forecast (including earlier refreshes), contract/category
  rows, periods within its horizon, permission-gated formats, task progress/cancellation and
  completed report links. Entity scope, book and currency basis follow the saved forecast.
  Completion refreshes the choice list; membership changes reset form state.
- Added paginated forecast-comparison-runs. It follows only successful scenario predecessors,
  checks current permissions, returns succeeded publications only and binds cursors to the
  current snapshot/workspace. Superseded/foreign lineage cursors are refused. OpenAPI regenerated.
- Five focused frontend checks, TypeScript/ESLint, Ruff/Mypy and the real scenario journey pass.
  The journey checks archived choices, pagination and invalid cursors, then runs JSON/XLSX/CSV/
  PDF report jobs and same-source rebuilding with no actuals. Populated accounting acceptance
  and rendered populated-report review are still outstanding. No deployment.

## Comparison report presentation — October 19, 2026

- Saved and rebuilt comparison controls now retain forecast ID, refresh time, book and currency
  basis. The viewer shows actuals cutoff, refresh time, variance definitions and a specific
  empty-actuals message; columns use the saved report's labels and order.
- Six focused calculation/rebuild checks, TypeScript and lint pass. Populated accounting
  acceptance remains open. Contract sample and period evidence packs remain development gaps.

## Contract sample event evidence — October 19, 2026

- Added the contract-sample event collector with exact contract/entity authorization, effective
  date and knowledge cutoffs, deterministic ordering, original-payload integrity checks and
  separate redacted-payload hashes. Superseded events remain in the evidence history.
- Produces per-contract event files, selected identity/date stamps and referenced source-record
  metadata. Shared raw import payloads are excluded; this is not document-byte collection.
- Targeted database collection/archive verification and two integrity/redaction checks pass.
  Computed versions/allocation/schedules, journals, decisions, audit slice, actual documents,
  stamped PDF/XLSX and public job/read/download integration remain. No complete-pack claim.

## Contract sample computation evidence — October 19, 2026

- Added immutable version history, allocation detail/trace and full schedule collection at
  the sample's effective date and knowledge cutoff. Combined-group companions are labelled
  and every contracting/performing entity is authorized; source scope is returned for retention.
- Validates trace digests/references and schedule counts/currencies/amounts. A real K01 command
  journey collects two obligations, future planned periods and an archive with event evidence;
  earlier-effective selection and revoked export permission checks pass. Ruff/Mypy pass.
- Public jobs, PDF/XLSX, documents, journal/approval/audit sections and combined-group acceptance
  remain. This collector is not a completed sample pack. No deployment.

## Contract sample approvals and audit slice — October 19, 2026

- Added cutoff-bound approval requests/decisions and deduplicated contract audit trails. Shared
  audit events authorize every linked contract; approval content requires its whole entity scope.
  Original decision hashes/MFA/delegation details are retained, credentials/contacts redacted.
- Computation evidence now supplies SSP/template and override approval references. The real K01
  journey verifies populated decisions/audit rows and combines them with events, allocation and
  schedule evidence into a hash-verified archive. Ruff/Mypy pass.
- This is a linked audit slice, not complete-chain verification. Journal/documents, source retention,
  public jobs/read/download, PDF/XLSX and broader historical/multi-entity acceptance remain open.

## Contract sample retained documents — October 19, 2026

- Added attachment collection for sampled contracts/events, related modification/estimate/
  adjustment evidence and referenced approvals/attachable subjects, including SSP studies.
  Applies the original attachment cutoff plus current subject/file grants; missing, unreadable
  or inconsistent bytes fail explicitly. External document URLs are never fetched.
- Deduplicates payloads, uses ID-based archive paths, retains filename/media/hash metadata,
  checks decrypted size/SHA-256 and takes file locks against concurrent shredding. File-count
  and payload limits apply before collection. The real K01 archive journey verifies encrypted
  attachment collection, duplicate references and safe paths; Ruff/Mypy pass. Public lifecycle/
  rendering and journals remain.

## Contract sample journal evidence — October 19, 2026

- Added journal collection through the existing retained grouping/drill-back reader, including
  aggregated lines whose contract ID is absent. Separates whole-line amounts from sampled
  contributions and checks source counts, cutoff/currency/entity consistency and net amounts.
- Resolves posting entities beyond contracting scope and authorizes every source companion.
  Retains as-of run/batch state, labelled cancellations and journal approval references.
- The K01 journey now commits real journal calculation, traces populated draft lines and
  reconciles source amounts in the combined evidence archive. Ruff/Mypy pass. Multi-contract,
  cross-entity and historical journal lifecycle acceptance remain; public retention/jobs and
  PDF/XLSX rendering are still unfinished. No deployment.

## Unified contract sample source snapshot — October 19, 2026

- Combined event/computation/journal/decision/document collectors at one cutoff; merged all
  dependency identities and permission scopes, including journal approval references. Captures
  a canonical scope alongside the source manifest in an encrypted SNAPSHOT_DATASET archive.
- Added typed immutable source binding/pack values and authorized retained reads. File metadata,
  bytes, manifest and embedded scope must agree; retries do not recollect business evidence.
- The real K01 journey persists a pack binding and encrypted snapshot, then reads it across UOWs
  with collectors disabled; digest tampering and revoked export scope are refused. Ruff/Mypy pass.
- Source-file deletion/retention registry integration must precede public release. Public create/
  worker/read/download, stamped PDF/XLSX and broader acceptance remain; no complete-pack claim.

## Contract sample dependency retention — October 19, 2026

- Added immutable tenant FK links from sample packs to captured snapshots and original
  documents (0188). Pack creation retains dependency files in the same transaction under
  file locks; retained reads refuse missing/extra/scope-inconsistent links.
- Integrated deletion holds and internal-only file ownership, preserving current document
  authorization. Also registered the existing forecast actuals capture file as retained evidence.
- The populated K01 sample journey passes with persisted dependency holds and missing-link
  refusal; 11 file-registry checks plus Ruff/Mypy pass. No broad suite rerun or deployment.
- Reporting remains feature work: public sample create/job/download and rendered PDF/XLSX/UI,
  period pack/relock completion, and populated actual-versus-forecast acceptance remain open.

## Contract sample PDF/XLSX assembly — October 19, 2026

- Added stamped nine-chapter PDF/XLSX workpapers from the authorized retained sample archive.
  Accounting grids show allocations, schedules, journal lines/contributions, events and documents;
  complete source-field tables preserve versions, trace nodes, approvals and linked audit evidence.
- Exact JSON values retain decimal precision, empty/null fields and long text in numbered parts.
  Unicode/control values use explicit escapes for the PDF standard font. Source file hashes and
  cutoff/basis notes accompany sections; binary originals remain byte-for-byte in the final ZIP.
- The populated K01 journey assembles both formats with live collectors disabled and verifies
  ZIP contents and unchanged originals. Precision/long-text check, Ruff/Mypy and PDF preview pass.
- Public sample create/worker/read/download and UI remain unfinished; rendering is an assembly
  component, not a claim that RPS-16 or the production-readiness goal is complete.

## Contract sample API and worker lifecycle — October 19, 2026

- Human requests can now create CONTRACT_SAMPLE packs through POST /evidence-packs, atomically
  retaining source dependencies, a stable render stamp and the EVIDENCE_PACK job. The worker
  rehydrates the active initiator's current grants instead of granting SYSTEM source access.
- Added atomic encrypted final retention, current-scope detail/manifest/ZIP reads and audited
  downloads. Successful retries reuse verified bytes; missing/damaged sources never trigger
  recollection. Existing failure/cancellation hooks settle sample packs too.
- Detail UI now handles sample contracts/cutoffs and scoped downloads; generated API schemas
  include the sample response. The register still lists CLOSE only; sample creation UI and
  sample-list pagination remain next feature work. Creation captures sources synchronously.
- Real K01 API/worker/download journey passes, including encrypted output, no re-render on
  retained reads, queued cancellation and permission-revoked terminal attempt/download refusal.
  17 evidence UI checks, 121 focused schema/file/storage checks, TypeScript, lint and Mypy pass.
- Fixed a stale transition-history function reference in period-pack journal collection; the
  existing real CTL-041 close-pack journey passes again.
- Broader multi-contract/combined-group acceptance and independent accounting sign-off remain.

## Contract sample creation form — October 19, 2026

- Added the sample-generation action to the evidence page. Users paste 1–50 exact external
  contract IDs (one per line), select an explicit effective cutoff, and submit through the shared
  idempotent command pipeline. Duplicate/blank-only IDs, excess counts and future dates are refused.
- All evidence permissions are required to offer the action; configuration permission is not.
  Server source-scope checks remain authoritative. Field refusals use the shared form mapping.
- Accepted requests open the sample detail page. If the response lacks its pack header, the
  form follows the job and recovers the result link without permitting duplicate submission.
- 22 focused generation/register UI checks, TypeScript and ESLint pass. The evidence register
  still lists CLOSE packs only; authorized sample-list pagination and discovery remain next.

## Contract sample history register — October 19, 2026

- Added sample history to the API and evidence page, with contract IDs, effective/known cutoffs,
  status, file count, manifest hash and links back to retained details/downloads.
- Counts and cursor pages include only packs whose full source/document scope is currently
  authorized. SQL prefilters entity scope; streamed composite checks avoid locking documents.
  Source-only internal bindings are excluded. CLOSE remains the default view.
- 14 focused PostgreSQL checks (including real K01 lifecycle/list), 34 evidence register/generation UI checks,
  TypeScript, Mypy and lint pass. No deployment.
- Reporting remains unfinished: broader sample accounting acceptance, period-pack completion,
  relock variance, change/access packs and forecast/report orchestration remain tracked.

## Re-lock variance report integration — October 19, 2026

- Close-pack creation now queues the existing variance-between-closes builder for re-locks.
  New v3 bindings retain the previous/current locks, report run and request cutoff; ordinary
  supporting reports retain the freeze cutoff. v1/v2 first-close bindings remain unchanged.
- Readiness waits for the variance job and audit verification; assembly includes the retained
  CSV, IPE manifest, source identity, original stored comparison and frozen measure changes.
  Frontend now permits re-lock selection and describes the additional evidence.
- Actual queue/worker/retained-output acceptance over seeded empty locks passes, as does the
  real first-close command journey. Focused binding/assembly checks and 34 UI checks pass.
- Still open: populated re-open/re-lock end-to-end acceptance, cross-contract driver evidence,
  catalogue PACK builders, change/access packs and independent accounting sign-off. No deployment.

## Change/access report-source implementation — October 19, 2026

- Added immutable CHANGE/ACCESS report-source preparation and retained collection. CHANGE
  captures configuration/SSP logs; ACCESS captures user-access/SoD reports, including removed
  members. All use explicit dates, known-at and captured entity scopes through the report framework.
- Original CSV, IPE manifest and source identities are verified and collected without requeueing.
  Current source/export permissions are checked on every retained read; newer entities are not
  silently added. Future dates and empty scopes refuse.
- Two actual PostgreSQL report-worker journeys and five date/scope checks pass; access output
  includes real memberships. Revoked export is refused; Mypy and Ruff pass.
- This is the retained report section, not completed CHANGE/ACCESS packs. Release evidence,
  role matrix/access reviews, parent retention/API/UI remain next development work. No deployment.

## Release provenance and access-role evidence — October 19, 2026

- CHANGE source v2 now captures requesting-process release registry facts and all registrations
  in the requested range, preserving recorded gates and explicitly distinguishing registered
  facts from original build-manifest bytes and independent approval.
- ACCESS source v3 now captures the complete role/permission matrix, including inactive roles,
  at its selected instant. Missing historical definitions refuse. Capture/read require
  tenant-wide evidence grants; a list of current entity IDs is not treated as that grant.
- Both emit fixed JSON evidence alongside retained report CSV/IPE outputs. Retries do not
  replace snapshots with current release/role values. v1 sources remain readable.
- Actual CHANGE/ACCESS report-worker collection and 17 focused checks pass; Mypy/Ruff pass.
- Still open: access-review evidence, parent job/storage, public CHANGE/ACCESS API/UI,
  populated re-lock acceptance and the wider reporting backlog. No deployment.

## As-of access-review evidence collection — October 19, 2026

- Added campaign/item evidence with original membership snapshots, counts and transition
  references. Historical output distinguishes pending decisions, requested revocation, confirmed
  revocation and later cancellation; future comments/reviewer identities do not leak backwards.
- Verifies source permission, snapshot hash/canonical bytes and complete member population.
  Uses tenant-wide access.approve, matching the source API, plus evidence permissions.
- Actual API create/start/decision/revoke/confirm/cancel collection passes. Seven focused
  timestamp/state checks, Mypy and Ruff pass. The audit slice is not full-chain verification.
- Collector returns personal payloads for encrypted storage; no personal source data is placed
  in source-binding JSON. Encrypted retention/dependency links and public CHANGE/ACCESS
  lifecycle/UI remain next. No deployment or production-readiness claim.

## Encrypted ACCESS review retention — October 19, 2026

- ACCESS v4 now includes encrypted retained review evidence, with only IDs, cutoffs, hashes
  and file metadata in source_binding. Reports, role matrix and review files collect together.
- Reuses the existing immutable pack/file registry for tenant-wide archive/original-file holds;
  retain() belongs to pack creation's transaction. Reads verify complete dependencies,
  campaign associations, current permissions and archive/scope integrity without recollection.
- Actual populated API review capture verifies encryption, source deletion holds, hidden generic
  file routes, hash refusal and repeat reads with the live collector disabled. CHANGE/ACCESS
  report-worker collection also passes; Mypy and Ruff pass.
- Next: parent job/storage and public CHANGE/ACCESS API/UI. No deployment or readiness claim.

## CHANGE/ACCESS evidence workflow — October 19, 2026

- Added atomic API creation, retained child-report readiness, current-requester worker
  authorization, encrypted final archives, scoped list/detail and verified ZIP/manifest downloads.
- Reporting now offers change/access generation forms, kind filters and retained detail pages.
  CHANGE uses inclusive dates; ACCESS requires tenant-wide evidence and access.approve grants.
- Real API → report workers → parent worker → list/detail/download passes for both kinds;
  retained repeat downloads keep original bytes. Targeted UI flows, types and lint pass.
- Still open: populated review campaigns through the complete parent flow, cancellation/revocation
  acceptance specific to these kinds, and wider RPS-16 accounting acceptance. Next reporting
  development: catalogue PACK builders and disclosure orchestration; remaining forecast work.
  No deployment or production-readiness claim.

## Catalogue evidence source/output adapter — October 19, 2026

- RPT-54/55 now have an internal adapter for an explicitly selected retained pack. It binds
  exact selectors, entity scope, source cutoff, source hash and pack/job identity; reauthorization
  refuses changed sources and requires current evidence permissions in every source entity.
- ZIP output preserves the complete original archive. Sample PDF/XLSX extraction preserves the
  retained chapter bytes and emits provenance linking the artifact to the pack manifest.
- Five focused archive/format checks pass; actual closed-period pack binding/read, altered-source
  refusal and revoked-export refusal pass. Ruff/Mypy pass.
- This is an internal adapter, not catalogue availability: ordinary report creation, persistent
  binding and dependency dispatch still need integration. The catalogue still refuses these codes.
- Reinspection confirms disclosure_pack already has child orchestration and a worker execution
  path. Its remaining acceptance gaps need auditing; do not describe orchestration as absent.
  No deployment or readiness claim.

## Catalogue evidence dependency/execution chain — October 19, 2026

- Ordinary report insertion now prepares and persists an explicit source pack binding in the
  initial INSERT, atomically with its jobs. Immutable report parameters/entity scope are not
  updated later. Retained preparation reuses the same pack; selectors and cutoff remain fixed.
- REPORT_RUN readiness waits for the exact EVIDENCE_PACK job and verifies its subject/hash.
  The worker rehydrates the current requester, verifies source access and stores the original
  artifact plus provenance through normal report completion/control recording.
- Real close acceptance exercises internal report creation, child reports/audit verification,
  source-pack completion and catalogue report worker completion; output bytes/hash match.
  Ruff and Mypy pass. Sample orchestration acceptance remains open.
- Public catalogue admission is still disabled: registration, lock resolution, source contracts
  and addressed/list/download authorization must be integrated before exposing RPT-54/55.
  Fresh sample capture currently requires the creation-time known_at; historical fresh capture
  remains unsupported (retained reruns preserve the original cutoff). No deployment.

## Public period evidence catalogue report — October 19, 2026

- Registered period_evidence_pack through POST /report-runs. Lock selectors reconcile to the
  frozen entity/book/period and cutoff; declared evidence permissions govern admission/scope.
- Standard list/detail/output/rerun and idempotent replay paths check current source access.
  Lists filter before counts/cursors. Direct framework output reads also reauthorize sources;
  generic file routes remain restricted to their existing report-output route.
- Same-source reruns preserve the bound evidence pack and original archive, with explicit
  provenance. Failed-pack metadata can still be authorized; readiness/download reject failure.
- Actual public API creation, dependencies, worker output, list/detail/download, limited-user
  denial and original-source rerun pass. Existing report lifecycle/rerun regression passes;
  Ruff/Mypy pass. User guide updated.
- Next: contract_sample_pack public catalogue admission and full sample orchestration acceptance;
  fresh historical sample capture and wider accounting/re-lock acceptance remain open.
  No deployment or production-readiness claim.

## Public contract sample catalogue report — October 19, 2026

- Registered contract_sample_pack with ZIP/PDF/XLSX and the complete evidence permission set.
  Catalogue creation uses the existing source-pack dependency, worker and current-source read
  authorization; source-document permissions still apply to metadata, lists and downloads.
- Threaded optional known_at through sample creation into the existing historical collectors.
  Generation timestamps stay current. Same-source reruns preserve the bound original artifact.
- Real K01 API → source pack → report worker → download/rerun passes for all three formats.
  A later attachment appears in current capture but not in historical PDF/XLSX sources;
  missing SSP-document permission hides rows before count/cursor, and revoked grants refuse
  downloads. Sixteen source-contract checks and Ruff/Mypy pass.
- Catalogue audit: 58 registered report codes; forecast_outputs is the remaining unregistered
  code. This is registration coverage, not full accounting or release acceptance. Next:
  forecast_outputs entry-point integration; broader multi-contract/re-lock/report acceptance
  and independent accounting sign-off remain open. No deployment or readiness claim.

## Reporting priority and saved forecast reader — October 19, 2026

- Reporting remains a feature-development priority. Catalogue registration counts do not
  establish report completeness or accounting acceptance.
- Added a format-specific saved forecast reader for the upcoming forecast_outputs catalogue
  entry. It reads retained JSON/CSV/XLSX datasets through scenario lineage and current export
  permissions, checks the parent and file identity, and decodes all five saved sections.
  It never recaptures the current scenario or substitutes a different format's disclosure.
- Eight focused forecast-export checks pass, including complete section decoding and rejection
  of changed/missing sections. The new database reader and public catalogue integration still
  need integration verification; forecast_outputs remains unregistered.
- Next development: wire forecast_outputs admission, immutable source binding, worker and
  report-centre access; then complete remaining report workflows and populated acceptance.
  No deployment or production-readiness claim.

## Bound forecast catalogue exports — October 19, 2026

- Added pre-insert forecast publication binding and per-use authorization. Bindings pin the
  forecast workspace, parent, published report, dataset file/hash and format; entity/book/
  currency scope must match. Historical cutoffs cannot silently select another publication.
- Refactored the existing JSON/CSV/XLSX renderer to render verified saved sections directly.
  Catalogue re-export uses the saved five-section dataset and current report stamp without
  reading today's scenario or recalculating forecast results.
- The real forecast-event capture scenario passes with binding and re-export of all three
  formats, identical retained dataset bytes/hash and rejection of changed format. Eight
  focused export checks and Ruff/Mypy also pass.
- Remaining: public catalogue admission, REPORT_RUN worker and read/list access integration.
  This is an internal completed path, not a publicly registered forecast_outputs report yet.
  Broader reporting workflows and accounting acceptance remain open. No deployment.

## Public forecast catalogue reports — October 19, 2026

- Registered forecast_outputs for JSON/CSV/XLSX through ordinary POST /report-runs and
  REPORT_RUN execution. Creation pins the completed publication before INSERT; execution
  reauthorizes the requester and renders all five saved sections without recapturing sources.
- Read/detail/list/download and cached-command access use current scenario/source grants.
  JSON data reads also authorize the bound publication. CSV remains a five-section ZIP;
  output_sha256 follows the forecast convention of hashing the canonical five-section dataset.
- Same-source catalogue reruns preserve the publication and dataset hash. Original forecast
  computation reruns remain explicitly unsupported; the UI/API must not imply recomputation.
- Real API creation, worker execution, download and rerun pass for all three formats; removal
  of scenario.use refuses retained-source access. Twenty-four focused source/export checks
  and Ruff/Mypy pass. User guide describes saved scope, format retention and hash semantics.
- Catalogue audit: all 59 definitions now have registered execution paths. This is not full
  report content, populated business workflow or independent accounting acceptance. Next:
  audit reporting feature/content gaps and complete the outstanding workflows, including
  multi-contract samples, reopen/relock, forecast comparisons and report-centre usability.
  No deployment or production-readiness claim.

## Forecast file-format viewing — October 19, 2026

- Fixed the report-centre mismatch where CSV/XLSX forecast detail requested section data but
  the data route accepted only JSON. Forecast file formats now read their own saved canonical
  datasets, with parent/publication/digest verification and current export authorization.
  Other report formats retain their existing data-route rules.
- The forecast history page offers inline figures for completed CSV/XLSX outputs when the
  viewer holds export permission for the report's entities. Original forecast publications
  and ordinary catalogue reports both use the saved format's visibility, without recapture.
- Real forecast workflow passes with original-publication reads and public catalogue section
  metadata/paged revenue rows for JSON/CSV/XLSX. Four focused UI checks and backend lint/type
  checks pass. Broader reporting features and accounting acceptance remain open.
- Next: continue the RPS/FCS reporting workflow/content gap audit; registration coverage is
  not a completion claim. No deployment.

## Actual-versus-forecast percentage display — October 19, 2026

- Completed RPT-40's signed variance percentage presentation. API values are already scaled
  percentages; the formatter shifts decimal strings exactly before percentage rendering,
  avoiding double scaling and numeric precision loss. Positive values show a plus sign;
  negatives follow tenant style and zero-base null values retain the no-value dash.
- Report columns now classify the comparison percentage as a right-aligned numeric value.
  Currency totals preserve the backend's saved variance percentage and render it as a
  percentage instead of treating it as currency or omitting it.
- Twenty-two focused format/report-grid/totals checks pass, along with TypeScript and ESLint.
  Populated production-posting accounting acceptance and other reporting workflows remain
  open; no full reporting or production-readiness claim. No deployment.

## Forecast comparison entry points — October 19, 2026

- The comparison form now defaults to the latest authorized succeeded forecast and its full
  saved horizon, matching RPT-40's specified initial selection. Explicit selection, parameter
  edits, submission and paging retain the selected record instead of following list refreshes.
- Each succeeded forecast history entry offers an inline comparison form preselected to that
  exact record, including a record absent from the current choices page. It preserves the
  saved entity/currency scope and only offers the entry with report access for every entity.
- Eight focused forecast/comparison interaction checks pass. Broader reporting content,
  populated accounting acceptance and independent accounting sign-off remain open.
  No deployment or production-readiness claim.

## Saved report column metadata — October 19, 2026

- Ordinary report grids now use saved column order where no dedicated layout applies, and
  use the saved title for fields without an existing translated title. RPO, waterfall and
  close/parallel comparison layouts retain their specialized section rules.
- Added saved date/timestamp/boolean types, decimal quantity versus integer formatting,
  actor display names and readable code lists. Nullable money fields keep their declared
  money type when their populated values are money objects. Legacy exports retain literal
  field naming and values; frozen textual data is not reinterpreted as a money object.
- Fifty-one focused report-page, grid and specialized-layout checks pass; TypeScript and
  ESLint pass. Reporting content and populated accounting acceptance remain open.
  No deployment or production-readiness claim.

## Report export recovery — October 19, 2026

- Export menus now guard duplicate submissions during the request, the accepted-but-not-yet-
  loaded job interval and job execution. Running jobs keep format choices visibly unavailable.
- Network failures and malformed accepted responses now show a recovery message. Cancellation
  has its own message. A completed export whose report record cannot be loaded offers a retry
  against the same report; it never queues another report or announces successful preparation.
- Three focused interaction checks cover duplicate requests, same-report recovery and network
  errors; TypeScript and ESLint pass. Other reporting workflows and independent accounting
  acceptance remain open. No deployment or production-readiness claim.

## Forecast run-record re-export — October 19, 2026

- Original succeeded forecast records now offer Re-export saved forecast instead of an
  unsupported new-computation rerun. The action creates a catalogue report with the original
  parameters/version/format, follows its REPORT_RUN job and opens the new record.
- Re-export navigation does not invent CTL-029 comparison results for an original catalogue
  creation. Bound catalogue reports retain the normal same-source rerun action; incomplete
  or unbound forecast records do not offer unsupported computation reruns.
- Forecast record and report-view stamps identify a saved forecast cutoff, and source text
  explains that exports reuse original figures. Twenty-six run-record checks pass, including
  the POST /report-runs action and navigation without a misleading equality banner.
- Broader reporting/business acceptance and independent accounting sign-off remain open.
  No deployment or production-readiness claim.

## Declared report parameter controls — October 19, 2026

- Removed the fixed-toolbar-only limitation for ordinary scalar/list report parameters.
  Declared strings, dates, integers, booleans, enums and arrays now receive controls after
  the existing ordered fields. Entity/book/period/source controls remain in their context UI.
  Contract-sample IDs, forecast references and close-comparison lock IDs can be entered on
  the report page rather than requiring manually constructed p.* URL parameters.
- New fields use declared titles or readable labels, required flags, date inputs, enum/boolean
  choices and comma-separated list help. Lists trim separator whitespace. Invalid integers
  and booleans are preserved for API rejection rather than silently converted/truncated.
- Forty-five existing report-page checks and three focused parameter checks pass, plus
  TypeScript/ESLint. Object-valued advanced filters and richer record pickers remain separate
  UI work; broader reporting and accounting acceptance remain open. No deployment.

## Report filters and saved-link preservation — October 19, 2026

- Added field/value filter rows to report toolbars whose schema declares filters. Users can
  add/remove conditions without entering JSON. Incomplete/duplicate fields remain editable
  and block live report submission instead of overwriting another condition.
- Report parameter conversion now produces the filters object; saved-report links retain
  string-valued objects. Previously opening a file report could omit its filters when creating
  the view run. Values containing punctuation survive the full saved-link round trip.
- Four focused toolbar checks and twenty-six run-record checks pass; TypeScript/ESLint pass.
  Backend authorization and supported-field validation remain authoritative. Richer record
  selectors, other reporting workflows and independent accounting acceptance remain open.
  No deployment or production-readiness claim.

## Saved report identity and entity scope — October 19, 2026

- Forecast CSV/XLSX Open report view links now retain run=<id>, using the saved-format reader
  instead of implicitly creating a JSON report (which may not exist for that forecast).
- Multi-entity links retain p.entity_codes alongside the all-entities context marker. Previously
  reopening a file report could expand the selected subset to every entity in the reader's scope.
  The toolbar displays the saved subset and provides an explicit Use all permitted entities action.
  Selecting a single context entity takes precedence over the saved subset.
- Thirty-three focused run-record/parameter checks pass. Other reporting business workflows,
  populated accounting acceptance and independent sign-off remain open. No deployment.

## Conditional reporting catalogue — October 19, 2026

- Removed the obsolete unconditional hiding of forecast outputs, actual-versus-forecast,
  migration reconciliation and parallel-run comparison. Forecast entries follow the existing
  sandbox/scenario-use access gate. Migration entries require migration.run and an authorized
  migration list with at least one record; unauthorized readers do not request that list.
- Forty-eight focused report-page checks pass, including workspace/access/empty-migration
  visibility, with TypeScript and ESLint. This completes catalogue access, not the remaining
  populated reporting workflows, accounting acceptance or independent sign-off. No deployment.

## Migration reconciliation workflow — October 19, 2026

- Replaced the empty migration Reconciliation step with a runnable workflow for opening-balance
  and replay batches: POST reconcile, persisted job recovery/polling, failure display and retry,
  and migration refresh at task completion. In-flight or successful reconciliation prevents a
  duplicate submission while the batch state refreshes.
- Imported/reconciled/submitted/promoted batches can navigate to this step. Report-authorized
  readers can open the retained reconciliation report or the report viewer with migration_id
  pinned, plus parallel comparison with the same batch selected. Period inputs remain editable
  in the report toolbar. Profile, promotion and other migration UI gaps remain separate work.
- Twenty-three focused migration checks, TypeScript and ESLint pass. Full populated accounting
  acceptance and independent sign-off remain outstanding; no deployment or readiness claim.

## Retained migration comparison lines — October 19, 2026

- Reconciled migration details now display retained contract/obligation comparison lines,
  legacy and eRev values, difference, tolerance, within-tolerance result, deviation reference
  and exception identifier. Decimal strings are preserved without guessing a currency or
  rounding small differences. The grid is available under migration read permission.
- Added an outside-tolerance filter using the authoritative flag, not nonzero difference.
  The query is scoped by batch, record version and filter; empty results and read errors
  remain distinct. Report exports continue through the report-authorized viewer links.
- Fifteen focused migration screen checks pass, including exact decimal rendering and a
  nonzero-but-within-tolerance case; TypeScript and ESLint pass. Populated accounting
  acceptance, other report workflows and independent sign-off remain open. No deployment.

## Migration report record selector — October 19, 2026

- Migration report parameters now offer searchable authorized records by migration number,
  mode, status and cutover date, with cursor-based loading of older batches. Choosing a record
  writes its exact ID into the existing report parameter flow.
- A saved ID outside loaded pages is retained. Readers without migration.run do not request
  migration metadata and retain the manual parameter field; locked parameters remain disabled.
  List loading, errors/retry and empty workspaces have explicit states.
- Eight focused selector/toolbar checks pass, covering older-page selection, retained IDs and
  permission gating, plus TypeScript/ESLint. Other report selectors, populated accounting
  acceptance and independent sign-off remain open. No deployment.

## Close variance snapshot selection — October 19, 2026

- Variance-between-closes parameters now choose Earlier close and Later close from authorized
  history for the selected entity, book and period. Options show the recorded timestamp,
  actor and approval number; only dataset-freezing LOCK records are offered, not REOPEN or
  PERMANENT_LOCK. Both selectors share the existing period-history cache.
- Explicit saved IDs remain intact outside the current context/list. Without a resolvable
  period or config.read scope, the manual parameter remains and no history read is made.
  Loading, empty and retry states are shown; the backend still validates source compatibility
  and chronological ordering before executing the comparison.
- Seven focused selector/toolbar checks pass with TypeScript/ESLint. Populated close-variance
  acceptance, remaining report workflows and independent accounting sign-off are still open.
  No deployment.

## Disclosure snapshot register — October 19, 2026

- Added /reports/disclosures and a Reports tab for report.run readers. The register queries
  retained snapshot metadata using entity/book/period context and disclosure-type selection,
  pages older records, and links each record to its original report run.
- Reuses the lazy verified snapshot detail panel. Draft versus locked source remains explicit;
  metadata browsing does not fetch all payloads or imply lock-time capture is complete.
  Source-status filtering was added in the subsequent source-filter update.
- Four focused register/detail checks pass with TypeScript/ESLint. Actual-versus-forecast
  populated-posting acceptance remains unproven; review found existing computation/cutoff UI,
  so no speculative calculation rewrite was made. Disclosure lock-time orchestration was
  already implemented (see archived publication/frozen-execution entries); the earlier status
  here was stale. Populated accounting acceptance and independent sign-off remain open.

## Disclosure source filtering and status correction — October 19, 2026

- Added API source=DRAFT|LOCKED filtering from immutable period_lock_id before pagination and
  counts, plus a source selector on the snapshot register. Updated generated OpenAPI/client
  types. The source state is computed from the record, never caller-supplied classification.
- Revalidated the real disclosure child/parent journey: draft list/count filtering, atomic
  locked snapshots, opposite-source empty results, frozen JSON/XLSX/PDF rebuild and retained
  reruns all pass in the existing database scenario with added source-filter assertions.
- Corrected stale status carried forward in recent notes/LIMITS: lock-time capture and frozen
  disclosure execution were already implemented in 54bb6fa / 41c8278. They are not remaining
  development work. Full populated accounting acceptance and independent sign-off remain open.
- Two focused register tests, Python typing/lint, frontend TypeScript/ESLint and the real
  disclosure journey pass. No deployment; the disposable verification database was stopped.

## Single-table PDF clipping fix — October 19, 2026

- Ordinary report PDFs now retain the compact layout only when every cell/header and source
  stamp fits. Otherwise they reuse the chapter renderer's wrapped rows, repeated identifiers,
  horizontal column groups and full source text. Large amounts and long identifiers are no
  longer silently replaced by ellipses. Existing chapter behavior is reused unchanged.
- Six focused output checks pass, including extracted large negative values/currencies,
  continued-page headers and footer page counts; Python typing/lint pass. Rendered a four-page
  wide sample and visually checked the first two groups: values, currencies and identifiers
  remain legible with no overlap. Wide reports may now use more pages.
- This fixes clipping, not the existing WinAnsi font character-set limitation. Full populated
  accounting acceptance and independent sign-off remain open. No deployment.

## Complete report catalogue coverage — October 19, 2026

- Compared frontend catalogue groups with current backend DEFINITIONS and found four missing
  entries: disclosure_pack, engine_trueup_register, upgrade_validation and ai_call_log_export.
  Added the first three to their business groups and normal report viewers. AI call log export
  opens its existing dedicated settings page and is visible only to settings admins/AI users.
- All 59 backend definitions now occur exactly once in catalogue groups. Conditional forecast,
  migration and AI permissions still apply; registration/visibility is not accounting acceptance.
- Forty-eight report-page checks pass, covering the added links and AI access, with frontend
  type/lint checks. Other functional gaps, populated accounting acceptance and independent
  sign-off remain open. No deployment.

## Scenario creation and forecast entry — October 19, 2026

- Added /reports/scenarios for production workspace members with tenant-wide scenario.use:
  named creation with purpose, async copy progress and refusal/network feedback, paginated
  active/archived scenarios, source cutoff and refresh timestamp. Creation uses the current
  production cutoff; accepted jobs prevent repeated submission while job metadata loads.
- Existing scenarios open through the established workspace-session switch, clearing the
  previous tenant's cache and then navigating to forecasts. The shared helper retains its
  original home destination for sandbox settings. Forecasts now link to scene management
  when a scenario workspace is required; a Reports tab exposes the new page.
- Eighteen scenario/sandbox checks and eight scenario/forecast checks pass (three overlap),
  plus frontend TypeScript/ESLint. Refresh/event editing, archive UI, populated forecast
  accounting acceptance and independent sign-off remain open. No deployment.

## Scenario archive and status filtering — October 19, 2026

- Active scenario records now offer an explicit archive confirmation describing read-only
  retained evidence. The POST carries the displayed row version; success refreshes the
  scenario cache. Backend creator/Controller authorization and idle-job checks remain
  authoritative. Refusals, version conflicts and lost responses remain visible without
  claiming success. Archived scenarios keep their workspace-read entry.
- Added URL-backed ACTIVE/ARCHIVED status filtering through the server's list filter before
  pagination. Creation still invalidates every scenario-list variant.
- Six focused creation/list/archive checks pass plus frontend type/lint checks. Refresh needs
  a published-input selector from the source scenario, and event-editing UI remains open.
  Populated accounting acceptance and independent sign-off remain outstanding. No deployment.

## Authorized scenario refresh choices — October 19, 2026

- Added GET /scenarios/{id}/published-inputs for production USER callers with tenant-wide
  scenario.use. Resolves an active source-owned scenario, checks its current active sandbox
  belongs to that production tenant, then lists only that scenario's published input versions.
  Tenant context is restored even on refusal; no arbitrary target workspace parameter exists.
- Returns only ID/code/name/version/hash/publication metadata, not captured API commands or
  uploaded payloads. Supports keyset paging/counts and no-store responses. OpenAPI and generated
  frontend types are updated. This supplies the missing refresh selector read contract.
- Real scenario/database journey passes current published choices, draft exclusion, paging,
  counts, hidden command payloads and sandbox-call denial; existing forecast capture/refresh
  checks also pass. Python lint/types pass. Disposable database stopped after verification.
- Refresh UI still needs input selection and refresh-stage tracking; event editing and wider
  accounting acceptance remain open. No deployment or independent-signoff claim.

## Scenario refresh reporting workflow — October 19, 2026

- Production scenario cards now select searchable, paginated published assumptions and request
  refresh with the displayed row version. The page explains replacement, guards pending
  submissions and displays durable QUEUED/RUNNING/SUCCEEDED/FAILED outcomes plus job details.
  Reopening the panel recovers an existing refresh; terminal outcomes reload scenario bindings
  and choices. A successful copy job alone is not used as proof of the complete refresh.
- Added source-owned GET /scenarios/{id}/refreshes with cursor paging/counts and no-store;
  returns outcome metadata only, excluding raw failures and replay/internal workspace payloads.
- Real forecast journey passes queued, failed and successful outcomes and sandbox denial.
  Eight focused scenario UI checks pass after correcting a test's tooltip/text ambiguity;
  frontend types/lint and backend types/lint pass. No deployment.
- Reporting remains unfinished: assumption editing/publishing UI, deal preview, populated
  actual-versus-forecast and close-variance accounting acceptance remain outstanding. Catalogue
  coverage is not completion of all reporting workflows or independent accounting sign-off.

## Forecast assumption lifecycle controls — October 19, 2026

- Forecast runs now include a lazy-loaded, paginated assumption manager within the existing
  scenario-workspace permission gate. Users can create a draft, rename a saved draft and
  explicitly confirm publication; published and superseded versions remain read-only.
- Shows captured-command/import counts, version/status and publication fingerprints. Empty
  sets explicitly identify baseline publication. Reusing a code invokes the existing backend
  next-version/copy semantics; an existing draft is handled by the server's refusal.
- Updates carry the saved row version. Publication refreshes the shared forecast input cache,
  making the new published version selectable for report runs. Lost responses preserve fields
  and permit idempotent retry; no optimistic publication state is shown.
- Eight targeted manager/forecast checks pass, with TypeScript and ESLint. Business-change
  capture controls, import attachment selection, effective-date editing and richer input review
  remain open; this implements lifecycle management, not the entire assumption authoring flow.
  Reporting accounting acceptance and independent sign-off remain open. No deployment.

## Forecast fact import entry and correction continuity — October 19, 2026

- Draft assumption records now link to the import wizard for import.upload readers, carrying
  the selected input-set ID. The upload page reads that set, displays code/name/version/status,
  blocks unavailable or non-draft targets before file upload and lists only backend-supported
  progress_events, usage, cost_events and invoices templates.
- Import creation retains the same forecast_event_set_id. Corrected-file navigation now keeps
  that association alongside template/mode; previously it silently fell back to ordinary import.
  Validation/commit and backend draft/permission checks continue to govern attachment.
- Seven focused import/assumption checks cover the link, displayed target, template restriction,
  publication guard, submitted ID and corrected-file identity. Frontend types/lint pass.
- This supplies forecast fact import authoring through the existing pipeline. Direct business
  command capture, richer input review and accounting acceptance remain open. No deployment.

## Captured forecast input review — October 19, 2026

- Assumption versions now expand a read-only review of captured contract event bodies and
  committed import sources in their retained interleaved application order. Event dates,
  obligations, payloads, comments and evidence IDs remain visible as captured; decimal strings
  are not coerced, rounded or truncated, and text is never interpreted as HTML.
- Contract/import links respect available read permission and use local routes. The page states
  that linked current records may differ from captured version evidence. Empty baselines and
  populated legacy sets without valid sequence evidence are explicitly distinguished.
- Six focused review/lifecycle checks pass, covering interleaving, exact numeric strings,
  literal markup, source links, missing order and baseline handling; frontend types/lint pass.
- Direct event-entry capture UI, effective-date controls, populated report accounting acceptance
  and independent sign-off remain open. Import sources use the existing authorized row viewer.
  No deployment or production-readiness claim.

## Direct forecast event capture from contract forms — October 19, 2026

- Existing delivery/progress/milestone/cost/return drawers now offer a paginated draft selector
  in sandbox workspaces with tenant-wide scenario.use. Normal approval remains the default;
  selecting a draft explicitly changes the action and explains scenario recording/replay.
- Submission carries forecast_event_set_id to the existing atomic capture endpoint, retains
  contract stream concurrency and evidence validation, then invalidates assumption reads.
  An unavailable selected draft blocks submission; the target is locked while submitting.
  Draft management links to contracts with instructions to select that draft in the event form.
- Ten existing/extended event-drawer checks pass, including the selected target in the request,
  retained-input refresh and forecast-specific success message; frontend types/lint pass.
- Usage/invoice input continues through forecast imports. Effective-date controls on input-set
  metadata, populated comparison/report accounting acceptance, deal preview and independent
  sign-off remain open. No deployment or production-readiness claim.

## Deal preview input and engine boundary — October 19, 2026

- Code inspection confirmed deal preview had only its persisted table, without an API,
  worker, engine adapter or screen. Added proposed-deal/create/save request schemas: exactly
  one customer identity/name, bounded nonempty lines, positive decimal-string quantities,
  nonnegative API money, one currency, strict positive terms and calendar-date input.
- Added pure deal_compute boundary using the complete revenue engine in DRY_RUN mode. It
  rejects multiple contracts or posted ledger baselines, preserves engine refusals, returns
  the full engine result/trace and verifies input/result fingerprints. No database writes.
- Four targeted schema/refusal checks pass. A separate real ASC606 kit-world computation
  confirms two USD 1000.00 allocations, DRY_RUN isolation and both fingerprints; lint/types pass.
- This is the compute foundation, not a working deal-preview feature. Authorized product/SSP
  resolution and bundle construction, retained audited jobs/API, result presentation, scenario
  save and SF-18 UI remain to implement. Tamsin acceptance and accounting sign-off remain open.
  No deployment or production-readiness claim.

## Deal preview authorized bundle assembly — October 19, 2026

- Added deal_bundle booking conversion and assembly: resolve the active contracting entity,
  enforce its scenario.use scope and functional currency, then use existing booking and
  bundle resolution for products, approved SSP, templates, policies and accounting books.
- Internal booking runs in a savepoint under system authority only after authorization. Both
  success and errors roll back temporary contract/group/customer/obligation rows and buffered
  audits; no computation persistence, file write or job enqueue is invoked inside the boundary.
- Proposed lines get stable keys and term end dates. Synthetic booking evidence uses the
  proposal's customer reference and sequence, removing rolled-back surrogate/sequence IDs
  that initially caused repeated-input fingerprints to differ. Calendar overflow is refused.
- Real database verification covers ASC606 allocation of USD 120000.00, repeatable input hashes,
  permission refusal, injected resolution failure and unchanged row/audit counts after commit.
  Python lint/types pass. Sequence allocation may leave harmless gaps after scratch rollback.
- Job/API retention, result presentation, scenario save and SF-18 UI remain unfinished, as do
  Tamsin acceptance and independent accounting sign-off. No deployment.

## Immutable deal preview retention — October 19, 2026

- Added retain service under a tenant/preview advisory lock. Every attempt rechecks scenario
  permission and entity currency. A matching existing record returns only after proposal and
  input/result fingerprints verify; reuse of an identity with changed input is refused.
- First execution resolves the scratch bundle and its reference index, uses the DRY_RUN engine,
  and stores the proposal plus complete engine bundle, full canonical result, both hashes,
  registered release ID and standard pinned_refs. Exactly one deal_preview.run audit is added.
  No commit occurs inside the service; the future worker owns attempt fencing and commit.
- Real database verification passes saved SSP references, exact request retention, repeated
  result identity, one audit and changed-proposal refusal alongside scratch rollback checks.
  Python lint/types pass. No production contract/customer survives the enclosing commit.
- Asynchronous request/worker wiring, authorized read APIs, user-facing result projection,
  scenario save and SF-18 UI remain unimplemented. No deployment or accounting-signoff claim.

## Asynchronous deal preview API and worker — October 19, 2026

- Added POST /deal-previews with idempotent command admission and a reserved preview identity;
  registered DEAL_PREVIEW worker execution. It reloads the active human initiator and current
  grants, uses fenced units of work, checks cancellation and retains the computed evidence.
  Already-retained previews refuse later cancellation; job results carry identity/hash/link only.
- Added scoped GET list and detail. Entity authorization filters before pagination/counting;
  lists return proposal metadata without engine traces, details verify input/result hashes
  and return retained result/pins without exposing the internal input bundle. Both use no-store.
- Migration 0189 adds deal_preview to the job subject constraint. Downgrade refuses while such
  jobs remain. Removed the pending-handler entry and retained registry negative-case checks.
- Real API/worker/database journey passes duplicate-request identity, successful USD 120000.00
  allocation, one retained preview, zero production contracts, summary/detail reads and entity
  scope filtering. Five registry checks, Python lint/types and OpenAPI generation pass.
- Scenario save, user-facing allocation/range/indicator projection and SF-18 UI still need
  implementation. Tamsin accounting acceptance, broader release verification and independent
  sign-off remain open. No deployment.

## Deal preview report presentation — October 19, 2026

- Detail reads now expose typed allocation rows, SSP bounds/range position, selected SSP,
  weights and adjustments, per-book transaction/allocation totals, material-right and variable
  consideration indicators, and revenue grouped by entity/period/subject. Only REVENUE
  schedules contribute; billing and costs are excluded. Currency precision comes from retained
  input evidence and all displayed money remains decimal strings.
- Scheduled and awaiting-trigger totals explain previews whose revenue schedule is empty.
  Projection uses hash-verified saved evidence, without resolving current configuration again.
  OpenAPI and frontend types are regenerated.
- Reporting remains a development priority. This completes only the result data layer; SF-18
  screen, scenario save, actual-versus-forecast populated K11 and multi-contract K03/close
  variance remain open. Tamsin acceptance and independent sign-off are also outstanding.
  No deployment; direct main workflow.

## Deal preview page — October 19, 2026

- Registered SF-18 at /contracts/deal-preview, enabling the existing Contracts list entry.
  Scoped users can enter existing/proposed customers, entity, start date, multiple product
  lines, decimal quantity/price, optional term and performing entity; currency follows entity.
- Asynchronous submission retains the job ID in the URL for reload/reconnect. Saved previews
  also open by preview ID. Result tables show per-book allocations, SSP bounds/range, weights,
  adjustments, indicators, scheduled/awaiting-trigger totals and entity/period revenue rows.
- Includes permission gating, input retention after network errors, retry controls, invalid-link
  handling and start-over confirmation. No contract creation or scenario-save button is implied.
- Nine targeted page/result/permission checks pass; TypeScript and ESLint checks pass.
  Scenario save, product-picker polish, revenue chart/period totals and real browser/accounting
  acceptance remain open. K11, multi-contract K03 and close variance remain Reporting priorities.
  No deployment; main-only publication.

## Deal revenue period matrix and chart — October 19, 2026

- Added per-product/per-period revenue matrix, period totals and all-period product/grand
  totals to SF-18. Entity/currency scopes are selected separately within each book; obligations
  for the same product aggregate while unassigned subjects retain their own identity.
- Added signed revenue bars with exact labels and an accessible table. Twenty-four periods
  display per page; page changes retain all-period totals and a fixed chart scale, and changing
  entity/currency resets the page. Awaiting-trigger balances are explicitly outside the schedule.
- Decimal-string totals use scaled BigInt arithmetic; only bounded chart ratios become Number.
  Grouping indexes rows once instead of repeatedly scanning the schedule for every matrix cell.
- Four focused calculation/render/pagination checks pass, including large signed amounts,
  mixed decimal precision, separate entity/currency scopes and cross-page totals. TypeScript
  and ESLint pass. Scenario save, product picker and Tamsin/browser acceptance remain open;
  populated K11, multi-contract K03 and close variance remain Reporting priorities. No deployment.

## Scenario-only deal preview save API — October 19, 2026

- Added POST /deal-previews/{id}/save. Requires an ACTIVE registered scenario whose current
  sandbox is the caller's workspace; production, ordinary sandboxes and stale scenario targets
  refuse with DEAL_PREVIEW_SAVE_NOT_ALLOWED. The scenario row stays share-locked through commit.
- Locks the preview, verifies saved input/result fingerprints, rechecks scenario entity access,
  and creates a normal DRAFT contract with contract.create validation, provisional computation,
  combination suggestions and holds. Updates saved_contract_id once and records the save audit.
  The original preview evidence is unchanged; the draft uses current reference validation.
- Real scenario/API checks pass first save, same-key replay, new-key duplicate refusal and DRAFT
  status; the production journey passes the explicit 409 refusal. Python types/lint and generated
  API schema pass. The UI save action and independent accounting acceptance remain open.
- Reporting correction from current code: Actual vs Forecast already has a registered builder,
  retained-source capture/rebuild, comparison calculation and UI entry. Populated K11 remains an
  acceptance gap, not an absent report implementation. K03/close-variance gaps still need specific
  code/evidence review before classification. No deployment; direct main publication.

## Scenario draft save UI — October 19, 2026

- Preview detail now advertises save_allowed only for an unsaved preview in an active registered
  scenario where the caller holds entity-scoped contract.create. The save command still locks
  and rechecks the scenario and preview; the read flag is not an authorization token.
- SF-18 exposes external-ID entry and Save as scenario draft only when eligible. Keeps input
  through network errors, uses the common idempotent command flow, invalidates preview/contracts,
  and presents the saved draft link after save or on reopening. Start over is blocked during save.
  Copy distinguishes current-reference draft calculation from retained preview evidence.
- Six focused frontend tests and two real scenario/production API journeys pass, including
  eligibility before/after save and production refusal. Python/TypeScript checks and lint pass.
- Product picker and real Tamsin/browser acceptance remain open; independent accounting sign-off
  is not obtained. Other report acceptance/implementation gaps remain under the broader goal.
  No deployment; changes go directly to main.

## Deal product selection — October 19, 2026

- Replaced manual product-code entry with the shared searchable combobox. Choices show code
  and name, include only active products, and follow the complete catalogue pagination.
  Every deal line must have an explicit valid selection before preview submission.
- Added catalogue loading/empty/refusal retry states. Product lookup runs only for new proposal
  entry; reopening retained evidence does not require current product catalogue availability.
  Start over clears selections and network retry retains the selected products.
- Four focused selector/submission/pagination checks pass; TypeScript and ESLint pass.
  Real browser/Tamsin accounting acceptance and independent sign-off remain open. Report gaps
  still require the broader implementation/evidence review. No deployment; main-only publication.


## Scenario refresh continuation fix — October 19, 2026

- Fixed a live Reporting workflow defect: acceptedJob previously remained pinned after its
  refresh appeared in the durable register. A later refresh then appeared to be a missing
  outcome forever, blocked new submissions and kept polling/displaying the old job.
- Acknowledged requests now release that local pin and follow the latest durable refresh.
  A terminal accepted job also releases it when a newer register row is dated at/after that
  job's completion, handling a completed refresh skipped between polls. Timestamp ordering
  compares instants, not lexicographic strings with potentially different offsets.
- Focused checks cover repeat refreshes, reopened in-flight work and a skipped terminal
  outcome followed by newer work. Existing backend authorization and row-version guards remain.
- Code review confirms variance_between_closes has prepare/replay/presentation and retained
  binding support. Its remaining business acceptance must not be described as absent code.
  Independent accounting acceptance and other release gaps remain open. No deployment.

## Forecast assumption effective-window editing — October 19, 2026

- Added optional UTC start/end controls to draft creation and editing, and saved-window display
  for every version. Blank edited boundaries send explicit null; untouched boundaries are omitted
  from PATCH, preserving original offset/precision when changing other fields.
- Invalid reversed/equal ranges block submission, and unsaved metadata changes block publication.
  All edits retain If-Match/version protection. Published versions stay read-only. Copy makes clear
  this is version metadata and does not rewrite captured event dates or filter replay events.
- Five focused assumption-manager tests pass, covering lifecycle, UTC conversion, preserving
  untouched timestamps, clearing boundaries and invalid-range refusal. TypeScript and lint pass.
  Remaining report/accounting acceptance and independent sign-off are still open. No deployment.

## Retained deal preview history — October 19, 2026

- Added a lazy, paginated history panel on SF-18 using the existing entity-scoped summary API.
  Displays creation time, proposed customer/reference, entity, start date, product codes and
  saved state; opens retained calculations and saved draft contracts in new tabs so current
  proposal input is preserved. The list does not fetch full engine traces for every row.
- Supports manual refresh and retry of a failed later page without discarding loaded entries.
  Preview completion and draft-save commands invalidate the shared history query.
- Seven focused history/page/save checks pass, including lazy load, cursor pagination, new-tab
  navigation and later-page retry. Types and lint pass. Broader business/browser acceptance and
  independent accounting sign-off remain open. No deployment; direct main publication.

## Tamsin deal acceptance and missing schedule fix — October 19, 2026

- Ran the FCS-6 Tamsin proposal against real published product templates and approved US-LIST
  2026-H2 ranges. SSP selection/range flags and 94,225.26 / 21,774.74 allocations already matched;
  the required November revenue schedule failed because the dry-run bundle stayed DRAFT.
- Deal computation now adds a deterministic hypothetical activation at inception to a single
  booking-only DRY_RUN input. The synthetic event stays in retained evidence, never the database
  event stream. Real save still creates a DRAFT. UI explicitly states the activation assumption.
- Added simulated revenue-to-calculation-date to per-book totals, so backdated proposals reconcile
  allocation = simulated revenue + future scheduled + awaiting trigger. Prior retained previews
  are not recomputed. OpenAPI/frontend types updated.
- Tamsin now passes exact SSP/range/allocation, no MR/VC, November start and deterministic input.
  API/worker journey passes no production contract and total reconciliation. Scratch rollback,
  four computation boundary checks, frontend rendering, Python lint/types and API generation pass.
  This is concrete FCS-6 case evidence, not independent accounting sign-off or full browser/release
  acceptance. No deployment.

## Reporting reference/FX attribution and GL tie-out — October 20, 2026

- Close variance now replays retained reference inputs before business events and FX rates
  afterward. Each phase retains its input/output hashes and changed fields; cell details expose
  the changed inputs. Original/final frozen endpoints must still match exactly. Group additions,
  removals/regrouping and calendar changes remain outstanding.
- Contract balances and balance rollforward now consume cutoff-qualified uploaded/pulled GL reconciliation
  role totals, compares each entity/role independently and retains those source facts for reruns.
  Missing sources, unsupported currencies and shared/unavailable role bases remain explicit;
  offsetting differences cannot pass. Viewer and XLSX/PDF expose comparison details.
- Necessary validation: 27 variance checks (including real-engine policy and FX changes), two
  GL comparison/rebuild checks, real upload/reconciliation/report and existing rollforward API
  journeys, and targeted viewer checks pass. Python/TypeScript checks are recorded with the commit.
- User priority remains completing attribution, multi-currency, RPO exemptions and GL matching.
  This is an implementation checkpoint, not completion of those four workstreams. Foreign-currency
  rollforward valuation, broader GL coverage, population replay and dated POL-200 exclusions remain.
  POL-199's zero royalty exclusion can be correct under the engine's realization model; the older
  blanket description of both exemptions as missing was too broad. No deployment.

## Dated functional contract balances and GL comparison — October 20, 2026

- Contract balances now reads retained engine functional targets at the selected period,
  preserving historical-layer liability valuation and monetary asset remeasurement. Foreign
  balances without dated evidence are refused rather than converted with a current rate.
- GL reconciliation uses the same dated targets. Actual EUR 10,000 receivable reports show
  USD 11,050 in August and USD 11,200 in September, both matching uploaded GL balances.
- Locked endpoints select computations available at the lock cutoff and verify the frozen
  transaction endpoint before projecting functional values; selected versions are retained
  for reruns. Locked-endpoint report/rerun and missing-evidence controls pass targeted journeys.
- Full functional movement attribution, reporting-currency translation, additional captions
  without engine functional targets, population replay and RPO partial exclusions remain open.
  This is a functional balance checkpoint, not completion of all reporting currencies. No deployment.

## Partial RPO targeted-VC exemptions — October 20, 2026

- POL-200 now excludes the dated targeted-VC quota only for wholly unsatisfied obligations
  with zero recognized revenue. Inception allocation nodes and later allocated deltas supply
  amounts; immutable estimate identities/version evidence distinguishes targeted from ordinary
  price changes. Fixed and untargeted consideration remain in disclosed RPO.
- Net bands and cell contributors are apportioned at currency precision. Reports list the
  excluded portion; dashboard uses the net amount. Frozen RPO retains net and excluded amounts
  on one obligation identity. Rollforward has an EXEMPTIONS movement for exclusion/release;
  close-variance replay shares the quota reader instead of refusing these elections.
- Three focused checks cover real-engine positive/negative/untargeted changes, historical caps,
  partial report rows and release on performance; 27 affected replay checks pass. Existing
  approved-policy and rollforward API journeys pass, with the new movement included. Lint/types pass.
- Full populated partial-exemption API/lock/export acceptance remains to be completed. This does
  not complete multi-currency movement translation, population replay or all release acceptance.
  No deployment; direct main publication.

## Independent group population changes in close variance — October 20, 2026

- Frozen close comparisons now support entire independent contract groups entering or leaving
  the population. The present side must reproduce its retained output hash and frozen money;
  the absent side is recorded as absent, with no fabricated empty input/computation.
- Entries use NEW_CONTRACT and exits OTHER with explicit population.entered/population.left
  evidence. Exits do not assert cancellation. Retained presentation and cell drill-through
  validate the available source and current contract access on either side.
- Existing groups still use event/reference/FX replay. A contract moving between groups or
  member additions/removals within a retained group still requires membership replay.
- The 27 focused replay checks pass, including real-engine group entry/exit, exact endpoints,
  presentation and cell source selection. Python lint/types pass. No deployment.

## Functional contract-balance movements — October 20, 2026

- Contract balance rollforward now supports functional currency using dated engine balances,
  posted functional control flows and historical billing-layer carrying. Revenue, reclassification
  and FX remain distinct. Closing balances and GL comparisons use the same functional basis.
- Both ERP and ENGINE billing use dated source documents; ENGINE amounts must match posted
  functional billing. Layer amounts must match retained, hash-verified trace nodes and transaction
  amounts. Consumed layer IDs are retained for reruns; missing evidence is refused.
- Settlement FX is placed immediately before its own invoice, with an equal adjustment to
  period-end FX, preserving posted net FX and avoiding a spurious liability/billing split.
- Targeted journeys pass: EUR receivable August/September with GL tie-outs, ERP and ENGINE
  invoice settlement plus rerun, locked-period functional movement and existing transaction
  invoice rollforward. ERP: opening USD 11,050 + FX 50 - billing 11,100 = zero. Lint/types pass.
- Remaining: FX attribution across multiple open monetary liability layers, combined-contract
  layer attribution, reporting-currency translation and broader report coverage. Ambiguous
  multi-layer FX remains refused. Full four-workstream completion is not claimed. No deployment.

## Reporting-currency contract balances — October 20, 2026

- Contract balances now translates dated functional balances into the tenant reporting currency
  using approved closing rates. Rows show functional currency and the closing rate; totals sum
  rounded contract rows. Currency precision uses exact rational half-up rounding.
- Rate amounts, row/version IDs and cutoffs are retained for reruns. Locked endpoints select rates
  at their frozen cutoff. Missing or ambiguous rates are refused; no runtime rate inversion or
  triangulation is performed. Balance and GL comparisons remain explicitly functional.
- Targeted API journey verifies USD 11,050 becomes EUR 9,945.01 at 0.900001; after publishing
  0.8, a new report shows EUR 8,840 and the retained rerun reproduces the earlier rows.
  Locked-period identity translation/rerun also passes; Python lint and types pass.
- Remaining: reporting-currency movement reports need opening/flow/closing rate treatment and
  explicit translation differences; broader report coverage, multi-layer FX and combined-contract
  attribution remain open. This is an incremental feature completion, not four-workstream closure.

## Reporting-currency contract balance rollforward — October 20, 2026

- Reporting view now uses the engine's S12-R-18 translation: preceding closing rate for opening,
  each posting period's average rate for movements, closing rate for closing. TRANSLATION and
  ROUNDING are explicit aggregate and by-contract lines, separate from FX_REMEASUREMENT.
- Intermediate functional endpoints and cumulative path deltas retain the original range's
  opening-liability identity across months. Rate/version facts are pinned per entity, period and
  type; locked endpoints use frozen cutoffs. Balance and GL comparisons remain functional.
- Unexplained functional OTHER fails the movement tie even if translation rounds it to zero.
  Missing flow periods or required rates are refused; no current-rate substitution on reruns.
- Targeted two-month API journey: EUR 10,000 closing, translated functional FX 180.59 and separate
  translation -180.59. Publishing a new closing rate changes a fresh run to EUR 8,960 while the
  original rerun retains its rows. Range-opening versus new-billing attribution is checked.
  Locked-period reporting and the existing balance translation journey also pass; lint/types pass.
- Remaining: broader reporting-currency coverage (including revenue/RPO), multi-layer monetary
  liability FX and combined-contract attribution; the other priority workstream gaps remain as
  previously stated. No deployment; this does not close the entire four-workstream request.

## RPO original-duration exemption — October 20, 2026

- POL-197 now uses original inception segments from verified retained computation inputs,
  matching the engine's inclusive service-date boundary (end before the first anniversary).
  Contract extensions and shortening no longer change the original-duration qualification.
- RPO, RPO rollforward, dashboard and close-variance projection share this basis. Reports show
  the original inception/end dates in the exemption detail and retain terms per source version
  for same-source reruns and cell explanations. Current templates/events never replace the input.
- Report jobs resolve the actual requester's source permissions; dashboard uses contract.read.
  Close snapshots use their explicit internal read-only SYSTEM path. Source integrity checks
  remain the same. No engine output or posting behavior is changed.
- Real-engine witnesses cover short-contract extension, long-contract shortening and the exact
  anniversary boundary; the existing partial-VC cases still pass. The API journey checks original
  dates, Home totals, cell explanation, retained rerun and read-only SYSTEM snapshot totals.
  Existing RPO rollforward and Python lint/types pass. Remaining RPO work includes
  broader positive partial-exemption lock/export acceptance and multi-currency reporting.
- Retained reports predating original-term evidence cannot silently reconstruct it from current
  data. Missing retained input/terms is refused; create a fresh report after source availability.
  No deployment; the four priority workstreams are not yet all complete.

## Revenue waterfall currency views — October 20, 2026

- Removed the foreign-contract refusal and the reporting-as-functional shortcut. Recognized
  revenue uses posted functional amounts; reporting translates each contributing revenue line
  using its posting period's approved average rate, preserving independent functional JE ties.
- Scheduled and awaiting-trigger amounts are explicitly forecast translations at the as-of
  period closing rate (transaction to functional, then functional to reporting). They do not
  restate historical revenue or value deferred-revenue layers. Rates/version IDs and rounding
  inputs are retained; future average rates are not required. Headers and cell details identify
  the forecast basis, and displayed cell contributions sum to converted totals.
- Necessary API checks cover EUR actual revenue, functional JE agreement, revised reporting
  average rates versus retained reruns, GBP future schedules performed by a USD entity,
  awaiting-trigger translation, and cell contributors. Existing cross-entity transaction
  waterfall and row-identity checks pass; Python lint/types pass. No deployment.
- RPO currency views, multi-layer FX attribution, combined-contract/group membership replay
  and independent accounting acceptance remain outstanding. Locked snapshots retain their
  existing transaction-currency schema; this change does not add alternate lock-dataset views.

## Revenue disaggregation currency views — October 20, 2026

- Fixed currency_view being ignored by revenue disaggregation. Functional view now reads posted
  functional amounts; reporting view translates each posted functional revenue line at its own
  posting period's approved average rate. Display totals sum the rounded line contributions.
- Rates/version IDs are retained per entity/period; locked endpoints use frozen rate cutoffs.
  Reporting journal tie-outs explicitly compare functional subledger and journal amounts before
  translation. The general journal-revenue reader now supports functional amounts without
  changing its default transaction behavior or retained run-membership rules.
- Targeted API journey: EUR 10,000 transaction revenue is USD 11,000 functional revenue; changing
  the reporting average to 0.8 yields EUR 8,800 in a fresh report while the original rerun keeps
  EUR 10,000. Functional journal tie passes. Existing transaction disaggregation control passes;
  Python lint/types pass. No deployment.
- Revenue waterfall and RPO currency coverage remain separate unfinished work, along with the
  previously documented multi-layer FX, combined-contract and difference-attribution gaps.

## Targeted VC evidence through the platform — October 20, 2026

- Fixed a missing production adapter path: the estimate element's allocation-criteria evidence
  now enters the engine input during previews and computations. Editable version parameters
  cannot replace or invent that evidence. The engine's existing POL-044 control is unchanged.
- RPO later-share eligibility now reads the element's evidence alongside the named version,
  rather than looking in version parameters where the product never saved that field.
- Positive API journey approves two targeted bonus versions, computes each, then verifies fixed
  consideration USD 132,000 remains disclosed while USD 20,000 is excluded. The witness uses the
  explicitly published tenant POL-044 NOT_ENFORCED election, with reviewed constraint evidence.
- Net time-band/cell contributors, snapshot producer rows and control totals, CSV export and
  retained rerun agree. A partially exempt obligation freezes as one section-1 row carrying both
  its net amount and exclusion metadata. Adapter checks also reject version-parameter overrides.
- This closes the populated partial-exemption report/snapshot-producer/export gap for this path;
  it does not assert a complete production lock workflow or all exemption combinations. Broader
  revenue/RPO currency views and the other documented reporting gaps remain. No deployment.

## RPO rollforward currency attribution — October 20, 2026

- Functional/reporting RPO rollforwards now translate month-by-month: business movements at
  monthly average rates and opening/closing disclosures at their own closing rates. Endpoints
  use the same per-obligation gross/exclusion projection as RPO, so partial-exemption rounding
  does not create mismatched closing totals. Approved rate identities are retained for reruns.
- FX is calculated independently from opening/closing exposures and rate differences; currency
  rounding has its own line. Source UNEXPLAINED remains separate, and any nonzero source monthly
  unexplained amount forces a failed balance tie even if display rounding could erase it.
- Necessary API witness covers three months of GBP/USD revenue and FX, both endpoint disclosure
  ties, a revised closing-rate set versus retained rerun, and injected unsupported movement that
  still fails the tie without changing FX. Existing transaction CTL-030 passes; lint/types pass.
- This completes the current RPO live-report currency path, not every reporting feature or
  alternate currency lock datasets. Multi-layer liability FX, group membership/combined-contract
  attribution and broader release acceptance remain outstanding. No deployment or accounting
  sign-off claimed.

## RPO disclosure currency views — October 20, 2026

- RPO now translates foreign transaction consideration to functional currency and then to
  reporting currency using retained approved as-of closing rates. The former foreign-currency
  refusal and reporting-as-functional shortcut are removed for the RPO disclosure report.
- Gross RPO and exclusion are translated first; net disclosure is their difference. Largest
  remainder allocation distributes net rounding through bands and contributors, preserving
  total = current + noncurrent = sum(bands) = sum(contributors), including partial exemptions.
  The source store remains untouched and the independent rollforward tie explicitly stays in
  transaction currency. Headers/control evidence/cell details state the as-of translation basis.
- Necessary checks: GBP disclosures translated to USD, currency-band/current conservation,
  converted cell contributors, published closing-rate revision versus retained rerun, POL-197
  excluded totals, and a foreign-functional partial-exemption cent-rounding witness. Existing
  approved targeted-VC journey and snapshot producer remain valid. Lint/types checked.
- RPO rollforward multi-currency movement/FX attribution is still outstanding, as are the other
  documented multi-layer FX and group-change attribution gaps. Existing locked datasets remain
  transaction currency. No deployment or independent accounting sign-off claimed.

## Layer-specific liability FX attribution — October 20, 2026

- Functional balance rollforwards now retain new billing layer identities and read verified
  liability creation/remeasurement movements. Period totals must equal posted control FX;
  missing layers, inconsistent traces/currencies or mismatched totals are refused explicitly.
- Opening layers retain their original range-opening classification; new layers remain separate.
  Revenue-relief FX precedes revenue and closing FX follows it. Billing settlement FX also carries
  its source layer identity. No functional-balance-weight apportionment is used. Source movement
  membership is retained for reruns; existing transaction paths and locked schemas are unchanged.
- Necessary real API witness: approved POL-163 override, one opening advance plus two new advances,
  monthly close FX, then delivery and a new close pass. Closing GBP 94,600 becomes GBP 55,900;
  revenue from opening is GBP 37,575, and balance ties pass. The pre-delivery report reruns unchanged.
  FIFO layer unit checks and ERP/ENGINE functional-invoice regressions pass; lint/types checked.
- This supersedes the blanket multi-open-layer FX refusal for attributable movements. Combined
  contract layer ownership and late-carried FX that cannot match dated movement evidence remain
  separate work, along with group-membership variance attribution and broader release acceptance.
  No deployment or independent accounting sign-off claimed.

## Isolated group-membership variance replay — October 20, 2026

- Close variance now detects connected group reorganizations and can attribute pure merge/split
  changes as MODIFICATION with explicit group.membership evidence. It verifies every original
  output/frozen endpoint, checks earlier groups at the later cutoff, and replays the new partition
  on the earlier contract-qualified posting basis before accepting the difference.
- Business events, contract terms, policy/reference changes and missing population sources are
  checked separately. Unchanged unions cannot hide a member's different group-policy basis.
  New bundle fields require an explicit comparison rule. Group-level posted amounts still need
  a redistribution basis; they are not reassigned by weight or replaced with empty computations.
- Per-contract execution aliases preserve distinct earlier/later computation and group identities.
  Report rows and cell contributors verify those identities against the authorized frozen sources;
  existing one-group and whole-population entry/exit evidence remains compatible.
- Necessary real-engine/frozen-CSV witness covers two differently priced contracts merging,
  reverse split, exact redistribution, presentation and cell sums/provenance. A simultaneous
  delivery is refused as a mixed change. Existing grouped replay/population/export checks pass;
  lint/types pass. This witness is not a full production close/lock workflow.
- Still open: simultaneous membership/business/reference replay, members entering/leaving a
  surviving group without a prior source, group-level posted redistribution, combined-contract
  FX ownership and late-carried FX. No deployment or accounting sign-off claimed.

## Membership plus business-event variance replay — October 20, 2026

- Group merges/splits can now coexist with newly recorded business events. The replay first
  evaluates the new partition without those business events, then adds consecutive event-driver
  runs in effective-date/sequence order. Late-event precedence remains explicit. Each phase
  retains its input/output hashes and source event keys; final metrics must match frozen values.
- The targeted real-engine witness now combines a nonzero merge redistribution with a late
  delivery. Membership effects equal the isolated merge; delivery effects equal an independent
  before/after engine projection. Report/cell amounts and retained source identities reconcile.
  Existing reverse split, population and export checks in the same journey pass; lint/types pass.
- This supersedes the simultaneous-business-event refusal below. Mixed contract/estimate record,
  policy/reference or FX changes, missing member sources, group-level posted redistribution,
  combined-contract FX ownership and late-carried FX remain open. This is authored frozen-data
  validation, not full lock-flow acceptance. No deployment or accounting sign-off claimed.

## FX after membership/event variance replay — October 20, 2026

- Reorganized groups now replay membership and business events on the coherent earlier FX
  basis, then apply the later source rates in a separate FX phase. Rates no longer have to
  remain identical across the two closes. Inconsistent earlier-group rate bases are refused
  explicitly rather than choosing one member's rates. Final frozen endpoint checks remain.
- The retained membership worker accepts an explicit transaction/functional projection, used
  consistently for original-source verification and every intermediate phase. Actual source
  and counterfactual hashes remain separate. Existing frozen CSV currency schemas are unchanged.
- Necessary real-engine witness merges two EUR contracts of a USD entity and revises rates:
  each contract's functional revenue increases by USD 60 under FX. Membership and FX effects
  independently equal their projected endpoint differences. Existing grouped replay, reverse
  split, mixed delivery, report/cell and export journey also passes; lint/types pass.
- Still open: alternate-currency frozen datasets and close-report integration; mixed contract/
  estimate/reference changes; missing members; group-level posting redistribution; combined
  contract/late-carried liability FX. No deployment or accounting sign-off claimed.

## Reference/policy phases with group changes — October 20, 2026

- Membership replay now reconstructs prior member policies for the new group, carrying only
  member-owned contract/obligation/contract-period policies and remapping group ownership.
  Shared prior policies and reference bases must agree; conflicts cannot silently become the
  baseline. Unknown policy scopes require an explicit ownership rule.
- The next OTHER phase applies later SSP/template/rule references and resolved policies together,
  before business events and FX. Execution hashes and changed-field names retain the basis of
  this attribution. Contract headers and estimate records still require separate handling.
- Necessary real-engine/frozen-data witness covers merge + RPO original-duration exemption
  election + late delivery, independently reconciles all three effects, and checks report/cell
  amounts and source details. Conflicting earlier policy bases are rejected. Existing reverse
  split and functional FX checks remain included. No deployment or accounting sign-off claimed.
- Remaining: contract/estimate record replay, incompatible earlier reference/policy bases,
  missing member sources, group-level posting redistribution, combined/late-carried liability
  FX, and alternate-currency locked datasets/close-report integration.

## Contract records and combined-template modifications — October 20, 2026

- Both ordinary and membership variance replay now introduce retained contract-record changes
  in the reference phase before business application events. Membership uses original member
  records first. Unique contract identities, transaction currency, contracting entity and inception
  must remain fixed; changing these requires an explicit basis migration instead of attribution.
- The real-engine merge + delivery + approved legacy prospective amendment witness uncovered an
  engine defect: the single-member template total was compared to whole-group TP. Templates now
  include unchanged members in the group check and preserve those members' posted allocations,
  assigning only the residual fixed-basis budget to the amended member. Final group checks remain.
- Necessary verification covers real monetary amendment effects, ordinary replay, isolated merge
  invariance, unapplied-record zero effect, late application provenance and unchanged other-member
  allocations/revenue/RPO (group balance attribution may change). Existing prospective/retrospective/POB-VC cases and basis-migration refusal checks
  pass; lint/types checked. This supersedes the blanket contract-record refusal below.
- Still open: missing member sources, incompatible earlier bases, group-level posted redistribution,
  combined/late-carried liability FX and alternate-currency frozen close integration. Broader release
  acceptance remains outstanding; no deployment or independent accounting sign-off claimed.

## Estimate versions in membership replay — October 20, 2026

- Group changes can now coexist with new approved estimate versions. The membership phase
  reconstructs the earlier contract/portfolio-owned estimate set; the reference phase introduces
  later versions before their ordered business application events. Original versions must remain
  unchanged and retained, and duplicate identities with different contents are refused.
- A real-engine/frozen-data witness combines merge, delivery and an added VC version/application
  event. Membership effects equal the isolated merge; introducing an unapplied version has zero
  effect; the dated application contributes the independently projected change under LATE_EVENT.
  The actual VC amount changes, all sums reconcile and application keys remain in the evidence.
- Necessary grouped journey also covers reverse split, RPO policy changes, conflicting policies,
  report/cell provenance and exports. Lint/types checked. This supersedes the blanket estimate-
  record refusal below; contract-header changes and incompatible earlier bases remain separate.
- Remaining: contract-header replay, missing member sources, group-level posting redistribution,
  combined/late-carried liability FX and alternate-currency frozen close integration. No deployment
  or independent accounting sign-off claimed.

## Explicit currency bases for snapshot producers — October 20, 2026

- SnapshotScope now carries an optional currency view. Producers normalize it through the
  actual report parameter schema, reject unsupported/invalid views and use the report's existing
  currency calculations. None preserves current defaults, including functional-only registers.
  Explicit-view output controls name the view and exact historical currency cutoff.
- Real database witnesses cover functional/reporting waterfall amounts (USD 11,000 / EUR 10,000),
  reporting RPO bands/totals and re-generation at the original cutoff after a revised approved rate.
  The latter follows the record clock before publishing the revision, so the temporal assertion
  is meaningful. Existing snapshot unit checks pass after updating stale adapter stub signatures.
- This is producer support, not completed lock integration: lock publication still stores each
  kind's default view, and as-locked currency selection remains unsupported. Next work must bind
  alternative datasets to immutable lock evidence and serve those retained variants, preserving
  existing default datasets and reconciliation behavior. No deployment or accounting sign-off.


## Immutable currency views at lock — October 20, 2026

- Public lock publication now retains transaction, functional and reporting variants for
  waterfall, contract balances and RPO in one manifest-hashed machine CSV per dataset. Per-view
  columns, controls and available rate evidence are authenticated inside that same file.
- As-locked API, report viewer and exports select retained variants without live recomputation.
  Old locks remain readable on their original basis and explicitly refuse missing alternatives.
  Relock comparisons expose functional/reporting changes separately from transaction changes.
- Necessary checks: actual public lock publication and populated K01 balances; retained API/CSV
  selection with the live builder disabled; 62 focused Python checks and 94 frontend checks;
  targeted lint, types and frontend compilation. No deployment.
- Remaining: alternate-currency rollforward/disaggregation lock datasets and close-variance
  integration, combined/late-carried liability FX, and other release limitations. This checkpoint
  does not complete all four reporting workstreams or provide independent accounting sign-off.

## Rollforward and disaggregation currency locks — October 20, 2026

- Extended immutable three-view lock storage, as-locked API/UI selection, CSV export and relock
  comparisons to contract balance rollforward, RPO rollforward and revenue disaggregation.
  Per-view schemas (including RPO translation rounding) and controls remain inside the hashed
  snapshot; report readers do not rebuild live inputs. Existing historical locks still refuse
  alternate views they never retained.
- Database checks cover each added report in all three views through API and exact CSV output
  with its live builder disabled, plus public empty/populated lock publication. A foreign-currency
  disaggregation witness retains EUR 10,000 transaction, USD 11,000 functional and EUR 10,000
  reporting revenue with rate evidence. Targeted fixture/unit checks, 94 frontend checks,
  frontend types and scoped lint pass.
- Remaining implementation includes close-variance currency selection and attribution against
  these snapshots, combined/late-carried liability FX and documented reporting/release gaps.
  No deployment or independent accounting sign-off; no production-readiness claim.

## Functional close-variance attribution — October 20, 2026

- Variance between closes now exposes transaction/functional currency selection. The selected
  basis flows through frozen endpoints, ordinary groups, membership changes, population changes,
  driver totals and presentation. Functional source identity and cell evidence bind the currency
  choice; old transaction bindings retain their original form. Migration 0190 updates the stored
  report schema so existing repositories receive the selector.
- Foreign RPO replay now values each obligation from retained positive closing rates, rounding
  gross consideration and exempt amounts separately before subtraction. Missing/ambiguous rates
  and historical locks without the selected frozen view refuse; endpoint differences are never
  hidden in OTHER. A real-engine EUR example gives USD 79.51 of RPO FX movement, including
  per-obligation rounding, and conserves all replay endpoints.
- Necessary checks: populated real-engine group replay against authored frozen bundles; retained
  currency selection and missing-view refusal; database worker/reauthorization/bound-rerun on
  empty published locks; frontend fixtures and scoped lint/types. These are distinct witnesses,
  not a populated foreign-currency public-lock acceptance test.
- Remaining: reporting-currency close variance (not offered yet), populated foreign-currency
  lock-to-lock acceptance, combined/late-carried liability FX and documented release gaps.
  No deployment or independent accounting sign-off; the overall objective remains unfinished.

## Retained reporting-rate projection — October 20, 2026

- Added a reporting-rate basis read only from verified WATERFALL, CONTRACT_BALANCES and RPO
  currency bundles. The basis binds source hashes and selected rate identities; balances must
  supply their own closing rate, conflicting retained conversions refuse, and nonzero revenue
  cannot borrow a closing rate when its average rate is absent.
- The replay projection now supports reporting amounts using per-line average revenue rates,
  separately rounded balance components, and sequential functional/reporting rounding of gross
  RPO and its exemptions per obligation. Original-source verification accepts this explicit basis.
- Necessary checks cover real-engine projected amounts and source reproduction, missing rates,
  corrupted snapshot hashes and conflicting metadata. A database witness reads all three actual
  snapshot producers and retains USD 11,000 -> EUR 10,000 revenue conversion. Targeted lint/types pass.
- This is the projection prerequisite: the public variance report still offers transaction and
  functional views only. Reporting rates must next be bound through each replay phase, with a
  separate reporting FX change (including unchanged engine inputs) and population/membership
  handling. Public reporting-currency variance, populated foreign lock-to-lock acceptance and
  the other documented gaps remain. No deployment or independent accounting sign-off.

## Reporting-currency close variance — October 20, 2026

- The public variance report now offers reporting currency (migration 0191). Ordinary replay,
  connected membership changes and independent population changes use authenticated lock rate
  bases. Business effects use earlier reporting rates; a final FX phase applies later reporting
  rates after any transaction/functional FX phase. Identical retained computations with changed
  lock rates produce FX effects, never a fabricated business event or PROGRESS residual.
- Replay evidence retains both reporting-basis hashes and marks the reporting_rates phase.
  Entry effects are valued at earlier rates before FX; exits remove the earlier frozen value.
  Currency/period basis changes and missing historical rates explicitly refuse. New reporting
  waterfall snapshots retain the selected period's average even when there is no revenue, so
  later population comparisons need not read current reference settings.
- Necessary checks: real-engine business/FX and unchanged-computation cases, population entry,
  combined-membership reporting replay against authored frozen datasets, and public empty-lock
  jobs with bound reruns/revocation. Actual empty lock publication verifies retained averages;
  68 focused registry/rate checks, 96 frontend checks and scoped lint/types pass.
- Still outstanding: populated foreign-currency public lock-to-lock acceptance, combined and
  late-carried liability FX, other documented reporting gaps and final release verification.
  Older locks missing required currency/rate evidence cannot be silently reconstructed.
  No deployment or independent accounting sign-off; production readiness remains unproven.

## Populated foreign-currency public lock — October 20, 2026

- The public lock witness now includes a EUR contract of a USD entity reporting in EUR. It runs
  actual close jobs and journal submit/approve/export/acknowledgement before requesting lock and
  obtaining a different Controller's approval. Frozen unbilled balances are EUR 10,000 in
  transaction/reporting currency and USD 11,050 functional. All monetary endpoints in all three
  views reproduce from the retained computation, after the source-read transaction closes.
- Reconciliation review rows remain test fixtures; this is not independent accounting approval.
  The domestic K01 public lock remains covered. This closes the single populated foreign-lock
  witness, not the still-outstanding two-lock foreign-currency report acceptance.
- Inspection for late liability FX found that S14 emits cumulative target differences and the
  ledger trace points to that target; fx_layer_key is not populated by the current product writer.
  The report's latest-version layer movements cannot simply be treated as those posted deltas.
  Next implementation must reconcile retained target/posted history and source-layer ownership;
  direct allocation from an assumed ledger layer key would be unsupported. Combined/late-carried
  liability FX remains unfinished. No deployment or production-readiness claim.

## Retained close-pass calculation evidence — October 20, 2026

- Found the underlying CLOSE-PASS-TRACE-1 gap: actual close-pass ledger lines have no contract
  version/trace record. Latest contract traces cannot establish what an earlier pass posted.
  Revision 0192 now retains each actual pass's typed input, explicit pass name, selected book
  output, trace and selected line fields in encrypted storage, atomically with its sealed
  posting. Group entry indexes distinguish pooled postings. Source reads check file, logical
  input/output and trace hashes and the selected ledger line; historical absence stays absent.
- Added immutable tenant-scoped links, file ownership/retention holds, privacy classification
  and scenario regeneration rules. FX pass/idempotence, populated foreign public lock and
  automatic netting reversal checks pass; evidence remains after recomputation. Mutation and
  cross-tenant checks, 12 scoped file-registry/census checks, lint and scoped types pass.
- Not complete: reporting must consume this evidence and reconstruct attributed paid history
  for combined/late-carried liability FX; existing historical passes cannot be silently rebuilt.
  A broader registry check also exposed pre-existing unclassified evidence_sample_file,
  forecast_actuals_capture, scenario_refresh and forecast/import fields, plus stale snapshot
  reference-count/excluded-column expectations. Those remain release work (four checks fail
  after updating the regenerated-table census). No deployment or accounting acceptance.

## Currency exports in close evidence packs — October 20, 2026

- Close/re-lock packs now include functional and reporting CSVs for all six retained currency
  snapshot kinds, alongside the existing transaction paths. Snapshot identities retain original
  bundle hashes/counts and list each delivered view's path, hash, row count and control totals.
  Each export uses its retained column schema and spreadsheet formula guard. Historical
  single-view locks remain single-view; no current rates or live rebuilds are substituted.
- Targeted archive checks cover actual snapshot production, legacy locks, manifest/hash/count
  refusal and formula guards. Combined/late-carried liability FX and populated foreign two-lock
  acceptance remain outstanding. No deployment or production-readiness claim.

## Historical paid FX and rollforward integration — October 20, 2026

- Close-pass evidence format 2 freezes the exact sealed FX control-line population read by
  the pass, including zero-net histories. The reader selects paid lines by retained role,
  currency, class, reason and origin/anchor periods, verifies their ledger fields and recursively
  resolves their retained close-pass deltas. Per-call memoization shares repeated dependencies;
  results bind every paid line and retained evidence hash. Format 1 remains readable but cannot
  establish automatic paid attribution; missing history refuses rather than allocating a plug.
- Functional/reporting contract-balance rollforwards now consume retained liability TIME
  deltas. Original creation dates keep opening/current-range layer identities, and group-level
  amounts follow source owners. New source bindings retain and recheck attribution dependencies;
  old bindings keep their original path. Asset-only FX remains on its existing path.
- Necessary checks passed: actual same-period second close after delivery, with nonzero prior
  paid amounts and explicit report source-binding assertions; original report rerun; the single
  liability close; ERP/ENGINE functional invoice paths; 25 focused projection/path checks and
  scoped lint/types. No deployment.
- Still open: command-computation paid adapters, mixed asset/liability target decomposition,
  combined-membership and late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final release/accounting acceptance. Current tests
  do not establish completion of all combined/late-carried FX or production readiness.

## Signed liability FX posting attribution — October 20, 2026

- Added a signed trace projection from retained S14 targets through S12 cumulative sums to
  actual liability layer owners. The posting calculation subtracts the prior target and
  explicitly supplied attributed paid layers, distinguishes TIME from EVENT, and verifies
  every intermediate sum, retained time component, paid total and final journal delta.
  Missing/corrupt sources, unknown split formulas and unprovided nonzero paid history refuse.
- The internal close-pass reader now resolves a selected sealed FX control line to its unique
  retained delta by target, posting period, currency and amount. Its evidence adapter keeps
  source identities scoped to the immutable close record rather than inventing version rows.
  A real GBP 5,400 close-pass delta reproduces with its actual contract/layer ownership. Two
  synthetic two-owner cases verify TIME/EVENT subtraction, differing owner shares and refusal
  of missing paid/source evidence. Scoped lint/types and these necessary checks pass.
- Still unfinished: selecting/authorizing and recursively attributing historical paid lines,
  command-computation evidence adapters, wiring attribution into rollforward presentation and
  acceptance for combined/late-carried cases. No report-completion or production-readiness
  claim; no deployment. Registry issues recorded in the preceding checkpoint remain open.

## Mixed asset/liability FX sources — October 20, 2026

- Signed control-target attribution now admits retained contract-asset and liability
  remeasurement leaves, preserving role, owner, layer and creation date through prior-target
  and paid-history subtraction. Functional/reporting rollforwards direct asset FX to assets
  even with a live liability layer; liability FX remains layer-specific. Same-day closing
  corrections net per role/layer before application, so UUID ordering cannot overdraw a layer
  when a later close reverses an earlier remeasurement.
- New reports bind control_posted_fx_v2. Historical liability_posted_fx_v1 bindings preserve
  their original asset-path choice. Migration 0193 updates the report IPE source catalogue to
  name encrypted close-pass evidence and recursive paid-line attribution.
- Necessary checks: actual reporting-currency asset rollforward/rate change/rerun, actual
  repeated liability close and report source binding, snapshot producer/migration checks,
  36 focused catalogue/trace/path checks, scoped lint/types. Synthetic mixed-target checks
  verify opposite asset/liability signs and asset flows that must not consume liabilities.
- Still open: command-computation evidence adapters and paid attribution, split-target
  formulas, combined-membership and late-carried public acceptance, populated foreign
  lock-to-lock acceptance, the recorded privacy/snapshot registry gaps and final accounting
  acceptance. A synthetic mixed target is not a populated combined-contract public witness.
  No deployment or production-readiness claim.

## Contract-computation FX evidence — October 20, 2026

- The shared FX attribution reader now adapts original command-computation input/output
  evidence as well as close-pass envelopes. It authorizes the complete retained group,
  verifies the encrypted source hashes, version trace and exact posting intent, and uses
  the original per-book seal cutoff to select historical paid lines. Version evidence keeps
  its real version identity; no synthetic close record or current-rate reconstruction is used.
- Paid attribution now follows actual command settlement and reversal histories recursively.
  Necessary checks passed: actual GBP 1,080 settlement and GBP 540 reversal with the original
  paid-line identity and both computation evidence hashes, plus scoped lint/types.
- Still open: public rollforward EVENT settlement timing must consume these sources without
  duplicating the existing before-invoice settlement flow and period-end offset. The TIME
  report path is unchanged. Split targets, regrouped/keyless historical subjects, combined
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded registry
  gaps and final accounting/release acceptance remain open. No deployment or readiness claim.

## Source-timed EVENT FX reporting — October 20, 2026

- Functional/reporting rollforwards now consume actual command EVENT posting deltas with
  original event sequence, source key, owner and asset/liability layer. Original and correcting
  postings net by dated source before walking the balance path. Billing settlement precedes
  its invoice; relief FX precedes revenue. New reports remove both old synthetic settlement
  movements, avoiding duplicate timing. Historical bindings retain the original path.
- New event_posted_fx_v1 bindings retain every command line, recursive paid dependency and
  evidence hash. Report execution rechecks its requester before authorized computation reads;
  close snapshots retain the restricted read-only SYSTEM path. Migration 0194 documents these
  source tables and semantics in the report IPE catalogue.
- Necessary checks: ERP and ENGINE foreign invoice rollforwards with source bindings and
  identical reruns; repeated liability close; command reversal and its net-zero report; scoped
  projection/path/catalogue checks and lint/types. No deployment.
- Still open: split-target formulas, regrouped/keyless historical subjects, combined-membership
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded privacy/
  snapshot registry gaps and final accounting/release acceptance. These ordinary settlement
  cases do not establish production readiness or all Reporting requirements.

## Regrouped FX source ownership — October 20, 2026

- Historical FX matching now uses S14's retained-membership regrouping rule. A stored group
  subject is compared under the computation's original member population; keyless legacy
  lines use that retained group/entity subject. Neither the sealed ledger fields nor the
  original source calculation is rewritten. Command intent checks retain exact stored subjects;
  only a missing subject uses the historical fallback.
- Necessary checks cover keyless settlement attribution, the actual reversal after the listing
  member leaves a three-contract group, and a two-contract public functional report. The latter
  assigns GBP 1,080 to the actual asset owner even though the ledger lists another member.
  The regrouping reversal retains the original paid-line dependency and delivered owner.
  The public August–September report after exit nets original/reversal/reposted FX to USD 200
  and passes the balance tie-out. Scoped lint/type checks pass.
- Scope correction: current control FX templates JET-10a/b/c select one role on each side;
  S14 does not emit split-weight targets for these flows. Unknown split formulas still refuse,
  but are not an outstanding feature for the current FX report path.
- Still open: late-carried public acceptance, populated foreign two-lock
  acceptance, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Group settlement/exit cases do not establish every membership transition or production
  readiness. No deployment.

## Exact paid-origin window for carried FX — October 20, 2026

- TIME FX historical attribution now selects the target period plus its immediately preceding
  continuous closed/permanently-locked run, bounded by the retained anchor. It no longer treats
  every period between sparse calculation targets as paid: an intervening open period stops
  pooling, matching S14. EVENT/ALL retain their exact source origin. All period states come from
  the original encrypted computation input; today's calendar does not change reruns.
- Necessary verification covers sparse targets across an intervening open period, a retained
  anchor inside a locked run, EVENT origin isolation and refusal of TIME in a non-postable
  period; the existing actual multi-layer repeated-close/report scenario checks integration.
  Scoped lint/types pass. No deployment.
- Still open: end-to-end late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final accounting/release acceptance. Correcting
  this selector does not establish those broader acceptance cases or production readiness.

## Foreign lock-to-lock business attribution — October 20, 2026

- Difference replay now holds operational period states constant after verifying both original
  computations and frozen endpoints. A public reopen no longer blocks late-event attribution
  as an unsupported entity change. Entity, currency, book population and calendar dates remain
  strict; the evidence records entities.periods.states normalization and the final replay must
  still reproduce the later frozen money, including posted revenue.
- Control FX projection verifies the retained settlement formula when S12 emits a zero
  difference node without a movement row. It does not discard zero cumulative sums, so
  offsetting owners remain visible; altered rate evidence refuses.
- Necessary verification passed: actual foreign close/export/acknowledgement/lock, two-controller
  public reopen, EUR 4,000 late invoice, actual second close/lock, and public variance jobs in
  transaction, functional and reporting currency. Each attributes the asset reduction solely to
  LATE_EVENT (EUR 4,000 / USD 4,420 / EUR 4,000) and retains normalization evidence. Reviewed
  reconciliation rows are fixtures, not independent accounting approval. Scoped unit checks,
  lint and types pass. No deployment.
- Still open: credit-memo FX difference attribution (JET-10c has a retained difference trace
  but no remeasurement movement leaf), end-to-end late-carried public acceptance without
  reopening, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  This populated foreign two-lock witness does not establish every FX or membership scenario.

## Credit-memo FX source attribution — October 20, 2026

- JET-10c attribution now resolves the original credit-memo difference trace into its
  retained liability reliefs, source owners, layer creation dates and event sequence.
  Each relief matches its original output and trace; the pinned rate and full difference
  formula are verified. Transaction portions are cumulatively converted in original trace
  order, preserving the once-rounded memo total and offsetting owner differences without a
  residual bucket or an allocation based on historical carrying value.
- Functional rollforward billing now uses the same retained spot conversion for those memo
  portions; actual posted EVENT FX adjusts each liability layer before its memo. Historical
  report bindings without the EVENT source path retain their former behavior. Derived source
  identities remain tied to immutable computation evidence and participate in paid-history
  subtraction. The engine and sealed journal amounts are unchanged.
- Necessary checks passed: actual single-layer and two-layer public memo/report workflows,
  ERP-imported and ENGINE-posted billing, source attribution and identical bound reruns. A
  USD 40,000 memo converts GBP 32,000 historical relief to GBP 33,600 at spot, with GBP 1,600
  FX and a GBP 40,000 closing liability. The two-layer full credit closes to zero with
  GBP 4,000 FX. Focused rounding/offsetting-owner and corruption checks, lint and types pass.
- Still open: public combined-contract credit-memo acceptance, late-carried public acceptance
  without reopening, recorded privacy/snapshot registry gaps and final accounting/release
  acceptance. This closes the ordinary JET-10c source gap, not every FX scenario. No deployment.

## Locked-period foreign invoice carry — October 20, 2026

- The populated foreign lock witness now also follows the no-reopen path: an EUR 4,000
  invoice dated August is recorded after the actual August lock, then September is closed
  through the public pipeline. Transaction, functional and reporting rollforwards all pass
  their balance tie-outs. The August lock remains the only lock/reopen record for its period.
- Frozen opening remains EUR 10,000 / USD 11,050; closing after the carried invoice is
  EUR 6,000 / USD 6,720. September's actual FX pass supplies USD 70 of remeasurement. Before
  that pass the functional report correctly reported the unposted difference; no residual
  or synthetic balancing entry was added to hide it. This closes the ordinary invoice/TIME
  carry acceptance gap using the existing implementation. Reconciliation review fixtures
  remain fixtures, not independent approval; no external GL trial balance is claimed.
- Still open: public combined-contract credit-memo and more complex carried EVENT correction
  scenarios, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Necessary verification is this actual lock/invoice/close/report flow plus scoped lint.
  No deployment and no claim that all Reporting or production readiness is complete.

## Combined-member credit-memo presentation — October 20, 2026

- Functional billing now reads source layers across the report's authorized members of the
  same immutable group version and entity. A credit memo can therefore price a relief whose
  layer belongs to another member, retaining the real source owner and movement identities.
- Added a combined-liability presentation bridge for in-range cross-member memos. It computes
  each endpoint's original layer carrying versus the engine's member presentation, then adds
  the known memo issuer/source transfers. Each original computation group must conserve zero.
  The independently derived amounts appear as RECLASSIFICATIONS; no amount is inferred from
  OTHER. Bound endpoint facts, movements and transfers are checked on rerun, including monthly
  reporting-currency paths. Historical bindings without the bridge retain the previous path.
- Fixed a separate false-PASS: unexplained OTHER on an individual contract now fails the
  movement tie-out even when opposing contract errors cancel in the currency total. Migration
  0195 and the IPE catalogue describe the expanded source scope, bridge and per-contract check.
- Necessary checks passed: public two-member memo consuming another member's layer, same and
  different historical rates, exact member closing/reclassification amounts, bound reruns,
  reporting-currency monthly projection, 27 scoped path checks and lint/types. The differing
  rate case closes at GBP 74,314.29 / 41,285.71 with GBP +714.29 / -714.29 reclassification;
  every member has zero unexplained OTHER. No deployment.
- Still open: general member reallocations without an in-range cross-member memo, more complex
  carried EVENT corrections, recorded privacy/snapshot registry gaps and final accounting/
  release acceptance. These cases do not establish every membership transition or readiness.

## Cross-member revenue relief and opening provenance — October 20, 2026

- Added retained positive-revenue layer transfers for combined members. The original trace
  identifies the recognizing contract while the movement keeps the consumed layer's owner.
  All liability reliefs must reproduce the affected recipient's entire posted revenue in
  every selected period before any transfer is admitted. Original lines, relief/creation
  movements, amounts and opening portions are bound for rerun. No remainder is inferred.
- The v3 member bridge includes those source transfers and classifies revenue by the actual
  consumed layer's creation date, not the recognizing member's own billing history. v1/v2
  bindings retain their original paths. Migration 0197 updates the rollforward IPE catalogue.
- Necessary public checks passed: another member recognizes USD 54,000 revenue using GBP
  43,200 of the first member's July advance; differing historical-rate member closings are
  GBP 74,571.43 / 29,828.57 with +2,571.43 / -2,571.43 reclassification and zero OTHER. Functional,
  monthly reporting and bound reruns pass. An August-start range classifies the GBP 43,200 as
  opening relief; a July-start range classifies it as current-range relief without changing
  total revenue or closing balances. Scoped lint/types pass. No deployment.
- Still open: the separate revenue_from_opening_liability builder reads amount_txn and applies
  its legacy same-contract cap; it must consume the multi-currency/source-backed relief path.
  Cross-member asset-creating, reversing, carried and other-control histories need their own
  posting-delta replay; this path requires full positive liability-relief reproduction and
  refuses unmatched histories. Recorded registry gaps and final accounting/release acceptance
  also remain. This is not full Reporting or production-readiness acceptance.

## Endpoint-driven member liability presentation — October 20, 2026

- New functional/reporting builds apply the retained member-presentation bridge to all
  foreign contract/entity endpoints, including periods without a memo or FX journal. This
  explains historical-rate reallocations when another member adds billing. The v2 binding
  records entity-qualified endpoint identities; v1 reruns retain their memo-triggered scope.
  Cache and member selection now distinguish entities so one contract cannot borrow another
  entity's carrying or presentation evidence. Migration 0196 updates the IPE description.
- Necessary checks passed: an actual two-member group with USD 90,000 advances at GBP rates
  0.80 and 0.84, no credit memo and no FX journal. Both members close at GBP 73,800; the
  independently sourced reclassifications are +1,800 / -1,800, and both OTHER amounts are zero.
  Functional and reporting views across August–September and their bound reruns pass. The
  existing monetary multi-layer repeated-close/report flow also passes under the broader
  source scope. Scoped lint/types pass; no deployment.
- Still open: cross-member revenue/other control-flow source transfers, more complex carried
  EVENT corrections and membership transitions, recorded privacy/snapshot registry gaps and
  final accounting/release acceptance. Generalizing the endpoint trigger does not establish
  those separate source-flow cases or production readiness.

## Opening-liability disclosure in functional/reporting currency — October 20, 2026

- New functional/reporting revenue_from_opening_liability requests now consume the retained
  balance path and original opening-layer attribution instead of silently reading amount_txn.
  Reporting openings use preceding closing rates; revenue flows use their period averages.
  The method, source populations and rates are bound for rerun. Earlier bindings keep their
  prior builder path; the transaction view is still the separate legacy implementation.
- The disclosure includes opening holders and recognizing members without capping a
  recognizer's valid combined-group relief at its own zero opening. Its footnote explains
  that distinction. Member/period source paths must reconcile before the disclosure is
  emitted, so unmatched paths cannot silently become disclosure totals. The IPE catalogue,
  source contract and migration 0198 document the additional sources and currency semantics.
- Necessary public checks passed: standalone disclosure totals and contract details equal
  the corresponding functional/reporting rollforward relief in the combined-member case,
  including GBP 43,200 recognized against another member's opening. July-start versus
  August-start ranges change opening/current provenance without changing recognized revenue.
  Reporting currency, summary opening totals and identical bound reruns pass; lint/types pass.
  No deployment.
- Still open: the transaction disclosure's legacy same-contract cap, per-obligation opening
  consumption, cross-member asset-creating/reversing/carried/other-control histories and the
  underlying posting-delta replay gaps. This new disclosure path currently requires reconciled
  source balance movements; pre-close paths with unposted FX are not accepted. Recorded
  registry gaps and final accounting/release acceptance remain; Reporting is not complete.

## Transaction opening-liability group consumption — October 20, 2026

- Positive transaction RPT-04 now pools control flows by retained computation version,
  entity and currency, assigning actual opening-layer consumption to the recognizing
  member. Earlier credit-memo debits reduce the available opening layer. Opening holders
  remain visible even when another member recognizes the revenue; groups and source
  method are retained for identical reruns. Migration 0199 updates the IPE description.
- Necessary verification: the combined-member disclosure reports USD 54,000 opening relief
  for an August-start range and zero for a July-start range, with unchanged USD 54,000
  recognized revenue and identical bound reruns. Existing single-contract results pass.
  All 28 control-path unit checks pass, including credit-memo consumption before revenue;
  implementation lint and types pass.
- Negative transaction revenue deliberately retains the existing net-reversal calculation;
  original reversal-source attribution remains unfinished. Per-obligation consumption,
  cross-member asset-creating/carried/other-control histories, pre-close unposted FX paths,
  recorded registry gaps and final accounting/release acceptance remain open. Reporting
  is not yet complete. No deployment.

## Signed revenue calculation sources — October 20, 2026

- Added exact signed expansion of retained S12 revenue cumulative targets, preserving each
  original movement, owner, layer and kind. The reader handles liability consumption, asset
  creation, asset settlement and liability creation, including negative contributions and
  opposing owners at a zero net target. Every intermediate total must reproduce its trace;
  missing, duplicate, cyclic, changed-amount or wrong-currency sources are refused.
- Combined-member revenue attribution now verifies selected relief against the complete
  signed target. New runs retain the source projection and movement population for rerun;
  existing bindings retain their earlier validation path. This connects the source reader
  to live rollforward and opening-liability disclosures rather than a standalone calculator.
- Necessary checks: real cross-member functional/reporting disclosures and bound reruns;
  six signed-source/corruption checks; lint and types. No deployment.
- This is the source expansion needed for further posting-delta work, not completion of
  negative-revenue reporting. Original/prior target and paid-history reconciliation, asset
  presentation transfers, per-obligation opening consumption and complex carried histories
  remain open. Final release verification and independent accounting acceptance remain open.

## Reporting and forecast data catalogue reconciliation — October 20, 2026

- Classified the 43 missing code columns across retained evidence-sample dependencies,
  forecast actuals captures, scenario refresh records, ordered inputs and import replay
  mappings. Business payloads remain confidential financial data; identifiers and lifecycle
  metadata follow the existing registry rules. Existing retention categories are preserved;
  proposed classifications still require owner acceptance, not implied legal approval.
- Added the missing scenario-refresh model section and explicit sample dependency columns;
  documented frozen import mappings. The catalogue now matches all 174 documented tables
  and every implemented column. Updated the strict documentation reader for the existing
  four-column table format and reconciled document order.
- Snapshot checks now explicitly verify that copied imports clear the regenerated forecast
  input-set reference and source-only mapping without mutating source data. The recorded
  reference-count/excluded-column drift and privacy registry failures are resolved:
  76 targeted catalogue and snapshot checks pass. No database migration or deployment.
- Remaining Reporting work is unchanged: original negative-revenue reversal attribution,
  per-obligation opening consumption, complex cross-member asset/carried histories and
  pre-close FX paths. Final release checks and independent accounting acceptance are open.

## Revenue posting-delta evidence and reconciliation — October 20, 2026

- Added revenue-line evidence reading alongside the existing FX adapter. It verifies the
  line against exactly one original retained posting intent in transaction and functional
  currency, verifies the trace/output and sealed posting, and captures the original
  pre-computation revenue population by ledger cutoff. Later/current lines are excluded.
- Added exact source-level target minus prior target minus paid reconciliation, including
  TIME, EVENT and ALL bases, negative amounts and owner-preserving cancellation across
  computation versions. Target totals, TIME components, paid totals and final delta are
  each checked. Source date and source key now accompany the signed layer projection.
- Ordinary revenue posting trace nodes are transaction-currency nodes; their functional
  amounts are separately retained. The reconciler therefore accepts verified explicit
  target facts rather than treating the transaction trace as a functional FX delta.
- Necessary checks passed: 14 focused source/delta checks and a real combined-contract
  sequence proving the later revenue envelope includes the prior posting but excludes its
  own posting; incorrect functional amounts are refused. Existing report reruns pass.
- Still required: wire verified functional target/time projections and recursive paid
  attribution into report presentation, including close-pass revenue histories. This
  internal reconciliation/reader addition does not yet enable complete negative-revenue
  reports. Per-obligation opening consumption, asset presentation transfers and final
  accounting/release acceptance remain open. No deployment.

## Cross-member revenue reversals through original posting history — October 20, 2026

- Ordinary revenue attribution now reads original transaction targets and their separately
  retained functional amounts, projects original owner/layer sources, and recursively
  subtracts the exact sealed paid-line population. Original role, period, TIME basis,
  ledger fields, computation hashes and all target/paid/delta amounts must agree. A shared
  per-report cache avoids repeatedly replaying the same immutable paid history.
- Live functional/reporting rollforwards and opening-liability disclosures use this proof
  for ordinary cross-member revenue. Source-proven reversals are now accepted when the
  complete posted owner/layer relief population equals the retained consumed-layer history.
  Dependencies and signed movements are retained for rerun. Earlier bindings keep their
  original path; intercompany entries retain their prior calculation and reversal limits.
- Necessary public scenario passes: three deliveries across two periods retain the prior
  same-period posting; a subsequent return reverses the original opening-layer owner's
  revenue. GBP 50,400 falls to GBP 46,800 for both recognized revenue and opening relief.
  Functional and reporting views rerun identically. Catalogue migration 0200, lint and types
  pass. No deployment.
- Still open: transaction disclosure reversal attribution, mixed TIME/EVENT functional
  source allocation, close-pass-only revenue history, asset/new-liability source presentation,
  per-obligation opening consumption and complex membership transitions. This completes the
  tested ordinary liability-backed return path, not every negative-revenue scenario.
  Final release verification and independent accounting acceptance remain open.

## Transaction-currency revenue reversal disclosure — October 20, 2026

- Ordinary transaction opening-liability disclosure now attributes negative revenue through
  original signed transaction source quantities and recursively verified paid lines. Original
  layer creation dates identify opening consumption; the recognizing member is not capped by
  its own opening balance. Reversal groups still must reconcile their complete control path.
- The shared source projection retains signed integer coefficients independently of rounded
  functional amounts, so a zero functional source does not erase a nonzero transaction amount
  or reverse its sign. No inverse FX conversion is used. Original layer dates are reconciled
  across historical computations; attribution caches cannot mix currency views.
- Reversal method, source identities, creation dates, paid lines and evidence hashes are bound
  for rerun, with an explanatory footnote. Earlier bindings retain their original builder;
  intercompany transaction reversals retain the earlier path pending counterpart attribution.
  Migration 0201 updates the disclosure IPE description.
- Necessary checks passed: the real combined-member delivery/return sequence reports
  USD 58,500 transaction revenue and opening relief, alongside GBP 46,800 functional values;
  transaction, functional and reporting reruns match. Existing single-contract results and
  catalogue migration pass. Fifteen source/delta checks, including zero-rounded source signs,
  and lint/types pass. No deployment.
- Still open: intercompany reversal attribution, mixed TIME/EVENT source allocation,
  close-pass-only revenue histories, asset/new-liability reversal presentation, per-obligation
  opening consumption and complex membership/carry histories. Final release verification
  and independent accounting acceptance remain open; Reporting is not yet complete.

## Retained revenue history for close passes — October 20, 2026

- Real period-end passes now freeze revenue paid-line identities and both original currency
  amounts alongside the existing FX population. The populations are distinct and covered by
  the same immutable encrypted evidence file and hash; an empty revenue population is explicit.
- Revenue attribution reads original close-pass evidence before falling back to ordinary
  computation evidence. A close pass lacking the new revenue population is refused instead
  of treating absent history as zero. Ledger role, selected line and retained hashes remain
  checked; recursive original-owner attribution and both currency views use the shared reader.
- Necessary checks passed: a real close release retains all original group revenue lines and
  their transaction/functional amounts; the existing FX close remains immutable/idempotent;
  combined-member deliveries, returns and report reruns remain correct. Three integration
  scenarios and scoped lint/types passed. No deployment.
- This completes capture/reader integration, not all close revenue scenarios. A nonzero
  close-only revenue posting still needs an end-to-end attribution scenario; mixed TIME/EVENT,
  intercompany reversal and asset/new-liability presentation remain open, as do the other
  documented feature/release gaps and independent accounting sign-off.

## Mixed liability relief and own-member asset revenue — October 20, 2026

- Functional/reporting cross-member revenue now accepts original sources that both consume
  another member's liability and create the recognizing member's own contract asset. The full
  posted revenue delta is verified; only liability-consumption sources must match retained
  owner/layer relief. Asset creation remains separately evidenced and is not opening relief.
- Presentation bridge v4 uses the verified total liability relief to correct local member
  replay that initially presents cross-member consumption as asset revenue. The amount comes
  from original source layers, never from OTHER. Opening/current-range relief, asset revenue
  and member transfers reconcile independently; original v1-v3 bindings retain their path.
- A real foreign-currency combined scenario consumes USD 45,000 of July advances and recognizes
  USD 54,000 in August, creating an asset for the excess. After the actual FX close, functional
  disclosure reports GBP 43,470 revenue and GBP 36,000 opening relief. Functional/reporting
  reruns retain their original source amounts. Catalogue migration 0202 describes this method.
- Necessary verification passed: the mixed-source scenario, existing multi-period delivery/return
  disclosure and reruns, catalogue migration consistency, scoped lint and types.
- Mixed TIME/EVENT source allocation remains open: S14 currently computes a proportional
  functional TIME amount without retaining per-source allocation. Do not infer TIME ownership
  from S12 source dates, which also represent EVENT revenue. Cross-owner asset settlement,
  new-liability reversal presentation, remaining close-only histories and other release gaps
  still need work. No deployment or production-readiness claim.

## Cross-period returns: asset settlement and new liability sources — October 20, 2026

- Original revenue attribution now presents the recognizing member's asset settlements and
  newly created liability sources as well as liability consumption and asset creation.
  Signed liability effects drive the member presentation bridge; newly created liabilities
  do not become opening-liability relief. Foreign-owner asset/new-liability sources remain
  refused until their separate transfer presentation is implemented.
- Bridge v5 includes cross-member relationships whose original consumption predates the selected
  range, so a return-month-only report retains the same original paid history as a full-range
  report. Earlier v1-v4 report bindings retain their scope and presentation path.
- Fixed S14 EVENT classification when a full return leaves zero cumulative transaction revenue
  but a nonzero functional amount from historical rates. A non-time-released obligation now
  keeps that amount in EVENT instead of incorrectly routing it into TIME because zero equals
  zero. This does not invent per-layer mixed TIME/EVENT attribution or repair old sealed journals.
- Real foreign combined scenario: USD 45,000 advance and USD 54,000 delivery produce GBP 43,470
  revenue, including GBP 36,000 original opening relief. A full September return at retained
  spot .84 reverses GBP 45,360, settling the asset and creating a new liability. Full-range net
  revenue is GBP -1,890; September alone reports GBP -45,360 and zero opening relief.
- Necessary checks passed: both currency views and identical reruns for full-range and
  return-month-only disclosures, the prior combined delivery/return sequence, catalogue
  migration consistency, 16 S14 checks, scoped lint and types.
- Migration 0203 describes the source method. Mixed TIME/EVENT source allocation, intercompany
  counterparts, foreign-owner asset settlement, remaining close-only histories and the other
  documented release gaps remain open. No deployment or production-readiness claim.

## Cross-member asset settlement from revenue returns — October 20, 2026

- Functional/reporting revenue returns can now settle another authorized group member's asset.
  The original signed posting replay identifies that asset owner and retains both sides of the
  settlement transfer. Asset settlement is never classified as opening-liability consumption.
- A new asset presentation bridge independently reconciles retained asset-layer carrying with
  presented contract-asset plus unbilled balances at each opening, closing and monthly endpoint.
  Creation, settlement and remeasurement amounts must match their original trace; member
  transfers and group endpoint differences must conserve zero. OTHER does not determine the
  adjustment. Every consumed layer and endpoint/source-transfer amount is bound for rerun.
- The revenue asset-source method is retained even when no transfer occurs, preserving scope
  on rerun. Earlier bindings keep their original method. Migration 0204 records the expanded
  report logic. Cross-member billing asset settlements still need their own source presentation;
  this change covers revenue-return settlements.
- The real combined foreign scenario recognizes revenue for two members and then returns the
  second member's delivery, settling the first member's asset at retained spot .84. The return
  generates GBP 45,360 of equal/opposite member transfers and zero opening-liability relief.
- Necessary checks passed: full-range and return-month-only functional/reporting outputs and
  identical reruns, the existing asset-to-new-liability return case, catalogue migration
  consistency, scoped lint and types.
  Mixed TIME/EVENT attribution, intercompany counterparts, remaining close-only histories and
  the other release gaps remain open. No deployment or production-readiness claim.


## Cross-member billing asset settlement and excess liabilities — October 20, 2026

- Functional/reporting billings now retain signed asset-settlement amounts and both sides of
  cross-member asset transfers from the original billing layers. Layer currencies, transaction
  totals, functional amounts and trace identities must already reconcile before presentation.
- Asset bridge v2 distinguishes billing that settles an asset from excess billing that creates
  a liability, including when the invoice issuer has no asset of its own. Both billing roles
  and corresponding member adjustments follow original source amounts, never unexplained OTHER.
  Monthly and whole-range amounts are bound; earlier asset-bridge v1 bindings retain their path.
- Billing and revenue-return asset transfers are combined without replacing either population.
  The billing source method is recorded even for empty populations, preserving rerun scope.
  Migration 0205 documents the expanded report logic.
- The real foreign combined scenario invoices USD 60,000 after another member recognizes
  USD 54,000: at retained spot .84 it settles GBP 45,360 of the other member's asset and creates
  GBP 5,040 of liability for the issuer. Asset balances close to zero; issuer billing remains
  split across the two roles and no member has unexplained OTHER.
- Necessary checks passed: asset and liability report views in functional/reporting currency
  with identical reruns, cross-member revenue-return regression, catalogue migration consistency,
  scoped lint and types.
- Mixed TIME/EVENT source allocation, intercompany counterparts, remaining close-only histories
  and other documented implementation/release gaps remain open. More complex membership and
  mixed billing/credit-memo histories still need end-to-end coverage. No deployment or claim
  of production readiness; independent accounting sign-off remains outstanding.


## Contracting intercompany revenue counterparts and reversals — October 20, 2026

- Revenue control attribution now resolves the contracting entity's INTERCOMPANY_DUE_TO leg
  within the same posting/entry/entity/contract. Original target, selected line, both currency
  amounts and recursively retained paid history must agree. It does not substitute the other
  entity's REVENUE leg or currency. Report evidence explicitly identifies the counterpart role.
- Ordinary computation history captures due-to lines at the original sealed cutoff. New close
  evidence declares the retained revenue roles; old close documents without due-to coverage
  refuse intercompany attribution rather than treating missing history as zero.
- Transaction reversal disclosure now uses the same original counterpart sources and separates
  asset/new-liability effects from consumed opening liabilities. Earlier legacy bindings retain
  their original builder. Functional/reporting intercompany relief uses the retained source proof.
- Presentation bridge v6 includes source-backed same-currency groups as well as foreign groups,
  including a return-month-only range whose original consumption predates the range. Earlier
  v1-v5 bindings retain their scope. Migration 0206 describes the expanded report logic.
- Real approved cross-company progress scenario: one member advances GBP 8,000; another member
  performs through AVM-US and recognizes GBP 4,000 in May, then revises progress to recognize
  GBP 2,000 cumulatively in June. Full-range opening relief remains GBP 4,000; June alone has
  GBP -2,000 revenue and zero opening relief because the reversal creates a new liability.
- Necessary checks passed: approved intercompany progress reversal in transaction/functional/
  reporting views, full-range and reversal-month-only identical reruns, ordinary cross-member
  return regression, real FX close evidence, catalogue migration, scoped lint and types.
- Mixed TIME/EVENT source allocation remains unimplemented in the generic close-release part
  interface. Current public ordinary revenue binding leaves released_at_close empty and posts
  relief as EVENT; do not infer TIME ownership from period-end source dates. Performing-side
  cross-calendar cases, close-only revenue histories, complex group changes and other documented
  release gaps still require work. No deployment or production-readiness claim.


## Reporting GL source navigation and inventory — October 20, 2026

- New GL tie-out details retain the source book and period key and link to that exact
  reconciliation in the viewer. Earlier retained evidence without the route metadata still
  renders its amounts without guessing a destination. Re-runs use retained source evidence.
- Incomplete GL comparisons also retain the source link and distinguish missing role,
  unstated amount, missing amount and currency mismatch. Two GL tests, lint and types pass.
- Corrected obsolete B4-3/4/6/8/12 and C-11 inventory claims: 59 of 59 definitions have
  execution paths (55 builders plus four composed reports). Registration is not accounting
  acceptance; the detailed scenario limitations and independent accounting review remain open.
- Necessary verification: two focused GL backend tests and the offsetting-role viewer test
  passed; backend lint/type checking and frontend TypeScript checking passed. No deployment.


## Retained TIME/EVENT input classes — October 20, 2026

- Engine traces retain each input's class and functional TIME total; reporting verifies
  both currencies before attribution. Internally mixed inputs remain unsupported.
- See [scope and verification](docs/release/REPORTING-SOURCE-CLASSES-2026-10-20.md).


## RPO exemption eligibility transitions — October 20, 2026

- Rollforward opening and closing now use their own retained versions for full exemption
  eligibility. A newly exempt closing cannot erase a disclosed opening; leaving an exemption
  is attributed to EXEMPTIONS. Obligations fully exempt throughout remain omitted.
- Four targeted cases cover entering, leaving, unelected and continuing right-to-invoice
  exemptions; endpoint balances agree with standalone RPO. Partial VC exclusions and original
  term evidence remain unchanged. Ten focused exemption tests and seven catalogue tests pass;
  backend lint/type checks pass. The database RPO rollforward tie-out test passes after migration
  0207, which aligns the stored report calculation description.
- This covers changes present in retained obligation versions, not historical policy-election
  changes or every public amendment workflow. Independent accounting acceptance remains open.

## Terminal cancellation RPO attribution — October 20, 2026

- Terminal cancellation now uses retained cancelled-version cumulative revenue to remove only
  remaining RPO. Current-period recognition and prior-period restatement stay in REVENUE and
  LATE_EVENTS. Subsequent cancelled versions retain the latest available revenue evidence.
- Four focused cases cover retained revenue, new revenue, late restatement and reversal;
  missing cancellation evidence is not replaced by a guessed recognized amount. This does not
  complete multi-exit/re-entry histories or competing cause decomposition.
- 21 focused exemption/cancellation/catalogue tests and the database multi-currency RPO
  movement/retained-rate test pass; Ruff and targeted mypy pass. Migration 0208 aligns the
  calculation description. No deployment or accounting sign-off.

## RPO cancellation and re-entry segments — October 20, 2026

- Revenue and late restatement are now measured within each retained disclosure segment.
  Re-entry adds the remaining balance, excluding cumulative revenue already recognized;
  changes while excluded do not become in-scope revenue. A range starting after cancellation
  does not recreate that earlier cancellation. Repeated cancellation/re-entry is covered.
- Cancellation attribution now also runs when the fixed allocation delta is zero, retaining
  recognition for obligations funded entirely by dated realized consideration.
- 29 targeted exemption, source-history and catalogue cases pass, plus three database cases
  for activation and late revenue after restoring the missing EXEMPTIONS zero-row expectation.
  Ruff and targeted mypy pass.
  Migration 0209 records the segmented calculation. These history-level cases do not establish
  that every public contract lifecycle can create every tested history; public lifecycle
  acceptance and competing cause decomposition remain open. No deployment.

## Event-backed mixed RPO changes — October 20, 2026

- Mixed modification/estimate versions now split original estimate-event allocations into
  VC_ESTIMATE_CHANGES and the remaining modification amount. Every event's shares must sum to
  its retained price delta; missing/non-routed events or incomplete shares stay unexplained.
- Signed changes and offsetting zero-net changes are covered. Dated usage remains separately
  attributed. Other competing cause sets and fully batched first-entry decomposition remain open.
- 32 targeted tests pass, including real engine estimate traces and missing-share rejection.
  DB currency/rate replay, lint and types pass. Migration 0210 matches catalogue. No deployment.

## Explicit measurement-only estimate evidence — October 20, 2026

- Stage 08 now retains whether an estimate changes measurement only, is absorbed at inception,
  or routes a later allocation change. The report accepts a measurement-only pin as explicit
  zero allocation impact after verifying its original estimate-version reference. Missing or
  legacy pins and inception changes remain unsupported for this decomposition.
- The flag is emitted after contract royalty-accrual routing is resolved, so those reallocating
  estimates are not incorrectly labelled measurement-only. No posting amounts were changed.
- The actual J-06 approval-to-report journey passes: September modification 150,000.00,
  VC change 200,000.00, revenue/restatement -91,463.41 and closing RPO 658,536.59 USD.
  This journey applies approvals separately; it does not claim one combined approval.
- 56 scoped engine/report tests, Ruff and targeted mypy pass. Migration 0211 updates the report
  calculation description. Independent accounting acceptance remains open; no deployment.

## First-entry batch estimate attribution — October 20, 2026

- Initial disclosure entry now separates later original estimate-event shares from NEW_CONTRACTS
  into VC_ESTIMATE_CHANGES, including signed decreases. Event dates and shares come from the
  original version's causes and retained trace; inception estimates remain part of entry.
- This path requires complete shares, all later changes through the range end, and no competing
  modification/cancellation. Earlier cuts before a batched fixed-price change still need dated
  fixed-allocation/remainder evidence; this change does not repair those earlier balances.
- 27 focused tests and the DB first-batch usage test pass; lint/types and migration 0212 checked.
  No deployment or independent accounting sign-off.

## Dated fixed allocation for historical RPO — October 20, 2026

- Stage 09 retains original fixed allocations by reporting period and version date, including
  returns. Historical reads reconcile this evidence to version remainders without counting
  return reductions twice; legacy traces keep their existing behavior.
- Earlier RPO excludes later fixed estimate changes. Same-version rollforwards attribute VC
  movements only when complete original event shares match the dated allocation difference.
  Positive and negative first-batch estimates are covered using real engine trace output.
- Historical future schedule reconstruction after later modifications remains open; the
  scheduled-remainder check still refuses unsupported schedules rather than prorating them.
  Compound competing causes and independent accounting acceptance also remain open.
- 109 focused tests plus two database report journeys pass; Ruff and targeted mypy pass.
  Migration 0213 describes the evidence. No deployment.

## Historical time-based schedule projection — October 20, 2026

- Stage 09 now freezes the original deterministic allocation segment at cuts before later
  fixed-allocation changes, retaining progress, exact targets and posted differences. RPO bands
  and revenue-waterfall future periods use this dated evidence and reconcile it to the remainder.
- Explain links name the exact cut, so a historical projected amount does not open the latest
  fixed schedule. The original retained schedule source remains available for drill-through.
- Real engine increase/decrease cases reproduce the pre-change future schedule by period;
  all trace nodes replay. Targeted report, reader and explain checks and two DB journeys pass.
- Still open: periods absent from the retained source schedule, missing original segment terms,
  adjusted/held cuts and broader compound lifecycle attribution. These paths retain explicit
  refusal, not proportional reconstruction. Independent accounting acceptance remains open.
  Migration 0214 records the calculation for RPO, its rollforward and the waterfall. No deployment.

## Historical periods survive removed schedule lines — October 20, 2026

- Original fixed period projections now have independent trace nodes, including periods whose
  current schedule line disappeared after a later allocation change. The engine projects over
  the retained performing-entity calendar and original segment term.
- RPO and revenue waterfall read these periods directly, reconcile their sum, and explain each
  through its obligation version, reporting cut and future period. Existing currency conversion
  uses the same projected contributions; no synthetic posted schedule line is created.
- A real engine case reduces the later allocation to zero: original January future amounts
  remain in RPO and waterfall even with no current schedule rows. Trace replay, trimming,
  incomplete-evidence refusal and explain selection are covered. 115 scoped tests and two DB
  journeys pass; lint/types and migration 0215 checked against all three IPE definitions.
- Missing original calendar/terms, held or manually adjusted cuts, legacy traces without the
  new evidence and complex mixed lifecycles remain open. Independent accounting acceptance is
  outstanding. No deployment.

## Dated recognition-hold remainder classification — October 20, 2026

- Stage 09 retains the scheduled remainder and its hold/pattern evidence at each measured
  period, plus a version-state reconciliation. Contract/report reads use that dated amount
  and derive awaiting-trigger remainder from the independently reconciled total.
- A later hold no longer changes an earlier cut's scheduled/awaiting split. Held cuts show
  awaiting-trigger remainder; release restores the time-based scheduled remainder. Future
  hold/release events also trigger the original-segment schedule projection for earlier cuts.
- Real engine hold-only and hold-then-release cases cover January before hold, February held,
  and March held/released; all trace nodes replay. Missing state/series and mismatched states
  are refused. 117 scoped tests pass; DB regressions and migration 0216 verified before publish.
- This does not complete arbitrary manual adjustment projection or combined hold/modification
  lifecycle acceptance. Legacy evidence gaps, missing original calendar/terms, broader mixed
  attribution and independent accounting sign-off remain open. No deployment.

## Original-cut manual schedule projection — October 20, 2026

- Fixed-only deterministic schedules now replay manual release, manual defer and schedule
  override formulas against original allocation segments and events effective by the report
  cut. Future manual changes and later estimate allocations do not backfill that projection.
  Every applied adjustment retains its formula, parameters and input chain for trace replay.
- Six real engine cases compare each adjustment kind with a later release or estimate change;
  projected future periods match the original pre-change calculation. Frozen contract-status
  cuts are excluded from time-based projection. 99 scoped tests pass, including hold/manual
  ordering and rejection of explicit unavailable evidence. Two DB report journeys, lint/types
  and all three migrated IPE definitions also pass verification.
- Mixed fixed/realized or netted adjustments and snapshots that cannot reproduce original
  revenue retain an explicit projection error; reports do not silently use the latest schedule.
  Missing calendar/terms, legacy evidence gaps, compound lifecycle/API acceptance and independent
  accounting sign-off remain open. Migration 0217 records scope. No deployment.

## Mixed TIME/EVENT input with unique source — October 20, 2026

- Stage 14 retains signed TIME amounts in both currencies for each single-input part. A
  multi-input part explicitly remains unresolved; the report introduces no allocation ratio.
- Revenue attribution can split an internally mixed input when every original source agrees
  on contract, layer, movement kind, effective date and source key. Both currency TIME totals,
  transaction sources, prior targets and paid history remain reconciled to original evidence.
- 35 scoped posting/source tests pass, including negative input amounts, offsetting TIME/EVENT,
  zero-net figures and ambiguous provenance rejection. Original S14 functional allocation is
  preserved. The DB intercompany progress-reversal journey, lint/types and both migrated IPE
  definitions pass. Migration 0218 describes the balance/opening-liability consumers.
- Mixed multiple-provenance sources, legacy traces without exact input amounts, split-role
  inputs and non-revenue components remain open. This is not acceptance of every public mixed
  workflow; independent accounting sign-off remains outstanding. No deployment.

## Retained subledger / GL / report bridge — October 20, 2026

- Balance and rollforward GL controls now expose retained subledger balances, subledger-minus-GL
  and report-minus-subledger per entity/role in functional currency. Either nonzero leg fails,
  even if the report and GL agree. Missing subledger evidence remains explicitly unavailable.
- The viewer shows both backend-calculated legs alongside the original GL source link. New v2
  bindings retain three-way semantics; v1 reruns preserve the original two-way control without
  live GL reads. Migration 0219 documents both consumers and repairs stale balance FX sources.
- Three focused backend cases, the viewer case and uploaded-trial-balance DB journey pass;
  lint/types and migrated catalogue checks pass. The foreign-balance DB journey fails during
  close DATASET_FREEZE before report comparison, including with the original GL implementation.
  That existing failure remains open; this is not full multicurrency acceptance.
- Multi-provenance TIME/EVENT attribution, broader lifecycle coverage and independent accounting
  sign-off remain open. Direct main publication only; no deployment.

## Foreign-currency close freeze restored — October 20, 2026

- FX source attribution now accepts S14's descriptive TIME/EVENT and per-input TIME annotations.
  Those annotations were incorrectly rejected as split-role parameters, blocking functional
  rollforward snapshot generation during close DATASET_FREEZE.
- Attribution still derives owner, signed amount and TIME/EVENT class from original S12 source
  layers; target/prior/paid reconciliation and genuine split-parameter refusal remain enforced.
- Seven focused source cases and the previously failing two-month foreign-receivable DB journey
  pass. The journey closes both periods and checks dated functional balances, FX movement,
  transaction-currency balances and GL controls. Two locked-endpoint functional/reporting
  rerun cases also pass with identical data, as do scoped lint and type checks. Broader
  split/mixed-source work is still open.
- The DATASET_FREEZE failure recorded in the preceding entry is resolved by this change.
  No deployment; independent accounting sign-off remains outstanding.

## Mixed revenue by retained recognition period — October 20, 2026

- S14 now retains per-input period classes from original relief causes, bounded by each target
  period. NORMAL is TIME only for close-released obligations; mixed periods stay explicit.
  Concession/multiple-input/split shares do not acquire invented classification evidence.
- Reporting can attribute mixed cumulative inputs across multiple owners/layers when each
  source period has a uniform class. It preserves original signed amounts and reconciles TIME
  independently in transaction and functional currency. FX readers accept the new annotation.
- 46 scoped engine/source cases, the DB intercompany progress-reversal workflow and two-month
  foreign-balance/GL journey pass. Scoped lint/types and both migrated IPE definitions match.
  Within-period mixtures, functional allocation mismatches, split/non-revenue inputs and broad
  mixed public-workflow acceptance remain open. Migration 0220 describes the two consumers.
- No deployment. Independent accounting sign-off and final release verification remain open.

## RPO exemption change detail viewer — October 20, 2026

- RPO rollforward now retains obligation-level opening/closing excluded amounts, dates, rule
  codes and the signed exemption movement. Full eligibility transitions and partial POL-200
  release use the same figures as the rollforward, without changing its accounting totals.
- Both report and run pages show a collapsible detail table with readable exemption names.
  Functional/reporting views explicitly label these original transaction-currency figures;
  the browser formats backend amounts without recomputing the movement.
- New source bindings opt into the details; legacy bindings retain their earlier output shape.
  Migration 0221 records the metadata. Focused policy/endpoint tests, the viewer case, lint/types
  and migrated catalogue checks pass. The DB multi-currency RPO journey also confirms retained
  exemption details after a rate revision and rerun. Broader reporting and independent accounting acceptance
  remain open. Direct main publication only; no deployment.

## Readable RPO exemption exports — October 20, 2026

- XLSX exports now render retained exemption facts as rows with readable policy names, wrapped
  text and numeric amounts, instead of one JSON cell that can exceed Excel's 32,767-character
  limit. PDF exports emit per-obligation endpoint and movement lines with existing pagination.
- A 120-obligation case larger than the cell limit retains the final record, all signed amounts
  and the transaction-currency basis. Text retains the formula guard; amounts are not recomputed.
  The CSV companion manifest retains the complete original facts without changing CSV columns.
- Focused export checks and lint/types pass. No accounting or report-total changes, no deployment.
  Remaining mixed-source functionality and independent accounting acceptance are still open.

## Split-role revenue source reader foundation — October 20, 2026

- The retained revenue reader now replays the original split role formula for a single uniquely
  owned revenue input. Both currency shares must match original weights, role index, side sign
  and minor-unit rounding. TIME/EVENT amounts and provenance remain independently checked.
- 36 scoped role-template/source cases and lint/types pass, including split rounding, mixed
  TIME amounts, changed transaction evidence and changed functional role amounts.
- Agent report integration is NOT complete: for_control still requires net revenue to equal
  gross control relief. Supplier history is absent from the close-pass revenue paid population.
  Next work must retain/verify AP_SUPPLIER and reconcile the separate gross/net components;
  removing the equality check alone would be incorrect. No public agent acceptance is claimed.
- Multiple-origin split inputs, other mixed-source gaps and independent sign-off remain open.
  Direct main publication only; no deployment.

## Agent gross/net reporting attribution — October 20, 2026

- Retained revenue histories now include only the AP_SUPPLIER purpose of revenue-recognition
  clearing lines. Close-pass envelopes declare that capability; older envelopes without it
  remain unavailable. Original intent, purpose and paid-history amounts are checked.
- Agent control relief is reconciled against separate net revenue and supplier components in
  both currencies. Original split formulas/rounding and unique source ownership are replayed;
  report evidence retains both component IDs and amounts without relabelling gross relief as net revenue.
- The actual merchant engine example reproduces 120,000 gross / 19,200 net / 100,800 supplier.
  The DB workflow exercises two deliveries, supplier paid history and public balance-rollforward
  and opening-liability reports in transaction, functional and reporting views with identical
  retained reruns. Intercompany reversal, 36 scoped cases, lint/types and migration checks pass.
- This supersedes the preceding entry's missing supplier-history/control matcher limitation.
  Multiple-origin split inputs, zero-net agent paths, within-period mixed-source attribution,
  and broad close-pass agent acceptance remain open; no overall production readiness is claimed.
  Migration 0222 documents the two consumers. Direct main publication; no deployment.

## Zero-net agent reporting — October 20, 2026

- A zero-net agent entry can now use its sole AP_SUPPLIER counterpart. No zero revenue line is
  invented. The entry must contain exactly the control and supplier lines; scope, currencies,
  original source amounts and both-currency balancing remain mandatory.
- Unsplit gross-billing targets now resolve original functional revenue sources. Retained report
  evidence identifies the supplier counterpart explicitly, preserving earlier nonzero shapes.
- The DB journey covers zero and nonzero fees, net posted amounts, original supplier history,
  both source currencies, and both public reports in all three views with identical reruns.
  No unexplained OTHER remains and balance tie-outs pass. Scoped lint/types pass.
- Migration 0223 describes this path. Multi-origin split and within-period mixed attribution,
  broader agent close/reversal acceptance and independent accounting sign-off remain open.
  The disclosure's existing gross-control-relief column policy is unchanged. No deployment.

## Mixed-period TIME source amounts — October 20, 2026

- S14 retains per-period transaction and functional TIME deltas from its original cumulative
  targets, including rounding and role signs. No posting amounts or allocation policy change.
- Reporting now handles a mixed cumulative input spanning periods/owners when each mixed period
  has one original provenance. That period's TIME/EVENT amounts use the retained pair, with
  both-currency total checks. Multiple owners within one mixed period still require finer evidence.
- Source tests cover signed foreign amounts, changed functional evidence, missing history and
  ambiguous owners. An original S14 mixed-period output feeds the report reader directly.
  Uniform-period legacy source ordering is preserved for retained reruns.
- Scoped source/engine cases, the DB intercompany reversal/public-report rerun journey, lint/types
  and migrated catalogue checks pass. Migration 0224 documents the two consumers. A dedicated
  public mixed-period workflow, multi-origin split and independent accounting sign-off remain
  open. No deployment; direct main publication.

## Public revenue cause / posting-class distinction — October 20, 2026

- Correction to preceding mixed-TIME entries: the production S13 costs_view explicitly leaves
  released_at_close empty for revenue (L3-2-Q-15). Deterministic NORMAL revenue and TP_CHANGE
  therefore post as EVENT. The schedule close-release flag is not the posting classifier.
  Conditional mixed-TIME support is an internal producer capability, not a presently missing
  public revenue workflow; do not change posting timing merely to exercise that capability.
- The actual public workflow uses a prepaid GBP service and an approved May bonus. Its May
  schedule separates NORMAL 3,224.18 and TP_CHANGE 445.05; public revenue/opening relief is
  3,669.23. Original counterpart amounts and EVENT-only target evidence are checked independently.
  Both public reports pass all three views and retained reruns, with zero OTHER and balance ties.
- Remaining live priorities include multi-origin agent split attribution and documented dated
  projection gaps. Independent accounting sign-off and final-candidate checks remain required.
  No deployment. This entry supersedes the earlier public mixed-TIME acceptance task.

## Agent gross relief across original source layers — October 20, 2026

- Two prepayment layers previously failed the split-role reader's unique-origin guard. Agent
  control attribution now falls back specifically on that ambiguity: gross control targets and
  original control paid history supply the source owners; net/supplier scalar targets and paid
  histories are independently replayed in both currencies. No per-owner net split is invented.
- Revenue history captures CONTRACT_LIABILITY only for REVENUE_RECOGNITION. Close envelopes
  declare that capability; older envelopes without it refuse the gross fallback. Both report
  consumers retain the gross control ID alongside component amounts and original evidence.
- The DB journey covers two 45,000 deposits, separate source layers, later supplier paid history,
  both public reports in all currency views and identical reruns. Single-layer and zero-net cases
  also pass. Scalar evidence has no movements and cannot masquerade as an attributed delta;
  changed functional split amounts fail. Scoped lint/types and source checks pass.
- Migration 0225 documents this path. Cross-contract agent groups, gross-control reversals and
  close-pass agent acceptance still need representative coverage; individual net/supplier
  source allocation remains unavailable without original owner evidence. Existing disclosure
  gross-relief policy and independent accounting acceptance remain open. No deployment.


## Agent refund and full-return reversal — October 20, 2026

- A real two-deposit refund/return journey exposed two engine defects: returned units did not
  advance the agent's latest transfer date (so a preceding credit memo was ignored), and a
  zero-weight role was omitted instead of clearing its old cumulative target. The original
  return quarantined with an unbalanced revenue-recognition entry; both defects are fixed.
- S10 now includes returned_cum changes as transfer boundaries. S14 retains zero-weight targets.
  Split-source readers validate explicit zero baselines only before any original functional
  source, using the retained calendar; missing later source history still refuses attribution.
- The DB journey posts the full reversal: USD 90,000 gross / 18,000 net / 72,000 supplier, with
  all three role balances zero in transaction and functional currency. September reports show
  negative gross revenue and zero opening-liability relief, with retained reruns in all views.
- Single-deposit and zero-net journeys, 63 scoped engine/source cases, lint and types pass.
  Cross-contract agent groups and broader close-pass acceptance remain open; this supersedes
  the prior unverified gross-refund/return case. Independent accounting acceptance and final
  release checks remain outstanding. Direct main publication only; no deployment.

## Combined-member agent refund reporting — October 20, 2026

- Fixed a real GBP 75,600 unexplained rollforward difference after a combined agent contract
  refunded its two deposits and returned all delivered units. A full return can erase prior
  consumed layers from the latest target; negative posted controls now identify recipients
  for original target/paid-history replay.
- Member billing classification now uses retained asset amounts including explicit zero.
  This moves liability-only credit memos out of the local member's apparent asset activity,
  without using OTHER as a plug. New source bindings preserve legacy report rerun behavior.
- The scenario funds agent deliveries from another contract's two USD 45,000 advances at .80;
  the agent's own advances use .84. Group allocation is independently checked, original source
  owners remain retained, and the full return preserves the USD 90,000 x .04 GBP difference
  in revenue/control rather than inventing a supplier balance. Both public reports rerun in
  all three currency views; the rollforward must tie across all members.
- Six scoped DB journeys and 35 report/catalogue unit checks pass, with lint/types and migration
  metadata checked. Migration 0226 updates the report's IPE explanation. Broader close-pass acceptance, dated
  mixed manual-adjustment projection, independent accounting acceptance and final release
  verification remain open. No deployment.

## Mixed usage manual projection — October 20, 2026

- Historical projections now freeze already-realized PERIOD_VC amounts and replay manual
  release, deferral and schedule override against the complete original-cut target. Later usage
  and later adjustments are excluded; changing realized amounts within the frozen horizon
  retain an explicit refusal rather than becoming a fixed forecast.
- Fixed-plus-usage overrides exposed an engine defect: after the last listed period, respread
  discarded the realized consideration and completed at only the fixed allocation. The anchor
  now includes already-realized consideration; usage realized after that anchor enters revenue
  immediately through a retained realized_delta parameter (legacy traces default to zero).
- Three adjustment journeys compare every historical future period with the original schedule,
  replay every trace node, pass through the contract trace reader, and reconcile to the dated
  scheduled remainder. Explicit checks preserve 1,200 fixed + 100 original usage at completion
  and recognize later 400 usage in its own month. Existing dated/fixed/manual paths also pass.
- 113 scoped engine/reader cases and 7 catalogue cases pass; migration 0227 was applied locally
  and all three IPE definitions match the catalogue. Lint/types pass. Royalty/netted mixed projections, broader
  public API lifecycle and close-pass acceptance, independent accounting acceptance and final
  release checks remain open. Direct main publication; no deployment.

## Original-cut royalty manual projection — October 20, 2026

- Added historical manual release/defer/override projection for fixed guarantees plus realized
  royalty components. Frozen snapshots filter both measure events and estimate pins by their
  original effective/application dates. Separate royalty projection nodes retain statement and
  accrual sources without duplicating live true-up nodes.
- Projections require stable original royalty sources, recognized amounts and guarantees over
  the frozen horizon. Unsupported source changes remain explicit refusals. The override anchor
  now retains recognized royalties, with subsequent signed changes separate from time respread.
- Six JPY journeys cover all three adjustment kinds, later statements above/below the guarantee,
  later accruals and releases. Every trace replays; future periods equal the original schedule,
  survive the contract reader, and sum to the original dated remainder. Downward corrections
  preserve the existing approved manual-release floor rather than bypassing S09-R-38.
- Related recognition/dated-reader checks and lint/types pass. Migration 0228 was applied locally;
  the three IPE definitions match the catalogue. Netted mixed projections, broader public API lifecycle
  and close-pass acceptance, independent accounting acceptance and final release checks remain
  open. Direct main publication; no deployment.

## Step-1 netted reporting forecasts — October 20, 2026

- Dated projections now freeze original deposit recognitions and apply the engine's existing
  Step-1 netting formula after manual adjustments. Every net target cites the attributed original
  deposit share; later adjustments cannot rewrite the historical schedule.
- Added a separate dated reporting remainder that excludes already-recognized 25-7 deposit
  revenue. The contract's stored cumulative measurement identity remains unchanged. Report
  schedule readers require projected periods to sum to the net remainder; zero means no future
  forecast. Legacy traces retain their original checks, without guessed deposit deductions.
- Six engine journeys cover release/defer/override with partial and full prior deposit revenue,
  replay every source chain and compare future periods with original schedules. Reader checks
  confirm the separate reporting basis and reject negative/excess balances. Related usage,
  royalty and historical-reader regressions pass (132 cases plus 3 new reader checks). Migration
  0229 applied locally and all three IPE definitions match; lint/types pass.
- Broader public API lifecycle and close-pass acceptance, independent accounting acceptance
  and final release checks remain outstanding. This completes the deterministic Step-1/manual
  projection path, not arbitrary source-changing or event-driven forecasts. No deployment.

## Reviewed GL source gate — October 20, 2026

- New contract balance and rollforward runs require reviewed/certified GL reconciliation
  sources. Draft, prepared, reopened or missing review states remain unavailable, with source
  identity and reason retained; matching numbers alone cannot produce PASS.
- Versioned v3 bindings freeze review status. Earlier v1/v2 bindings retain their original
  arithmetic controls without live reads. Reopening a source changes new runs, not retained
  historical reruns.
- Eleven focused comparison/binding checks and two public API journeys pass, including
  draft/review/reopen, deterministic reruns and dated foreign functional balances. Migration
  0230 updates both IPE definitions. No deployment; broader lifecycle/accounting acceptance
  and final release-candidate verification remain outstanding.

## Filterable GL bridge workpapers — October 20, 2026

- Excel exports now render GL tie-out evidence as a filterable table, one row per retained
  entity/role. GL, retained subledger, report closing and both bridge differences are numeric
  cells with amount precision; review state, source ID, book/period and unavailability reasons
  remain separate columns. No balances or differences are recalculated during export.
- Missing evidence stays blank, distinct from zero. Equal/opposite bridge differences remain
  visible with FAIL even when the net difference is zero. Text retains formula protection.
- Single reports and disclosure workbooks share the renderer. Focused workbook and existing
  export checks pass; production renderer lint/types pass. Independent accounting acceptance
  and final candidate verification remain outstanding. Direct main publication; no deployment.

## Dated revenue-waterfall population — October 20, 2026

- New waterfall calculations exclude contracts entering after each performing entity's as-of
  period end. Entry comes from the first included version along the contract's membership
  chain and the book-specific activation/criteria/opening event, using the existing historical
  entry rule (fallback: that version's effective date). Later measurements do not delay entry.
- Entry dates and source-version identities are retained in versioned evidence. Bound reruns
  do not read current entry events; old bindings and already-frozen datasets retain their
  original population. Missing entry evidence is refused, not replaced by inception guesses.
- Public API checks cover March exclusion/April entry, retained reruns, performing-entity
  journal tie-out, restricted entity access and dated FX. Both regrouping computation orders
  pass. A pure retained-binding check covers differing calendar endpoints and legacy behavior.
  Migration 0231 updates the waterfall IPE and source list; scoped lint/types pass.
- B4-1/C-3's population implementation gap is closed. Independent accounting acceptance,
  broader lifecycle acceptance and final candidate verification remain open. No deployment.

## Reporting-currency balance aging — October 20, 2026

- Fixed reporting view returning untranslated aging amounts when transaction and functional
  currencies coincide. Supported functional age buckets now translate at approved retained
  closing rates, with currency/rate columns and source evidence in control totals.
- Cumulative bucket rounding conserves the translated contract/role total, including signed
  amounts and tiny balances. Functional balance reconciliation remains separate and explicitly
  labelled. New bindings retain translation behavior; legacy bindings keep original output.
- GBP-to-USD public report/rerun, existing asset/unbilled aging and later-billing rerun journeys
  pass. Focused core/catalogue checks, lint/types and migration 0232 roundtrip/IPE agreement pass.
- Foreign transaction-to-functional aging still requires exact functional layer attribution;
  this path remains unavailable. Locked aging datasets, independent accounting acceptance and
  final candidate verification remain open. Direct main publication; no deployment.

## Original functional aging layers — October 20, 2026

- Foreign asset/unbilled aging now reads original S12 reclass shares in functional currency,
  retaining the original S10 revenue date. Missing, wrong-currency or unlinked share evidence
  is refused; no report-side FX ratio is applied to those balances.
- Liability aging uses signed functional creation/consumption/remeasurement amounts from the
  selected version's immutable layers. Historical carrying and the approved monetary override
  preserve original creation dates, including partial consumption.
- New functional bindings retain this source path. Each member/role must match its dated
  functional balance before display; unmatched combined-member ownership remains unavailable.
  Reporting translation follows the existing retained closing-rate/cumulative-rounding path.
- Four API journeys pass: EUR unbilled dated remeasurement and reruns, historical and monetary
  USD/GBP liability layers with partial consumption, and reporting translation compatibility.
  Targeted core checks, lint/types and migration 0233 roundtrip/IPE agreement pass.
- A separate diagnostic exposed S04-R-02 failure after over-billing a right-to-invoice contract;
  it is recorded in LIMITS for follow-up. Locked aging datasets, combined-member allocation
  expansion, independent accounting acceptance and final candidate checks remain open.

## Priced right-to-invoice advance billing — October 20, 2026

- Fixed the shared RTI source selector: a booked unit price selects delivered quantity even
  before the first delivery. Advance invoices therefore cannot become performance revenue,
  and later delivery cannot switch from an invoice-based price to a performance-based price.
- Stage 04 allocation and stage 09 recognition use the same corrected source. Rated usage
  retains priority; invoice fallback remains available when no unit price/performance source
  exists. Existing stored outputs are unchanged until a new computation is requested.
- Whole-engine checks cover before delivery, after delivery and additional billing, asserting
  price/allocation/revenue together. Related RTI/source/recognition checks pass (25 cases).
  The previously failing EUR case now computes: EUR 20,000 billed, EUR 10,000 earned, with
  USD 5,500 and 5,550 remaining in their original liability-age buckets. The public aging
  report reconciles. Scoped lint/types pass. No deployment.
- This closes the S04-R-02 diagnostic recorded in the functional-aging checkpoint. Broader
  combined-member aging, locked aging datasets, accounting acceptance and final release
  verification remain outstanding.

## Locked balance aging — October 20, 2026

- New closes freeze BALANCE_AGING alongside the existing twelve datasets. Original age buckets,
  transaction/functional/reporting amounts and reporting FX controls are authenticated in the
  manifest. The viewer supports retained currency selection; CSV exports and close evidence
  archives read only those bytes. Additional aging filters cannot alter a locked population.
- Re-lock comparison measures each aging bucket and total by entity, contract, role and currency,
  including a move between buckets with an unchanged total. Existing twelve-kind manifests remain
  verifiable/exportable; old locks without aging explicitly refuse that report, with no live backfill.
- Migration 0234 adds the snapshot enum and IPE metadata. Targeted API read/export, real foreign
  close-run freeze, public lock, new/legacy evidence archive, re-lock and viewer checks pass.
  Scoped lint/types and migrated catalogue parity pass. No deployment; direct main publication.
- This does not fill missing original layer evidence: combined-member functional aging whose
  owner layers do not reconcile still refuses. A new close now also requires its aging dataset
  to be reproducible; historical computations missing the required traces can require recompute.
  Independent accounting sign-off and final-candidate release checks remain open.

## GL reconciliation review table — October 20, 2026

- The report viewer now presents retained GL comparisons as a table: GL, retained subledger,
  report closing, both bridge differences and the net difference. Each row keeps its comparison
  and bridge results, source review status and original reconciliation link. Functional-currency
  scope is stated explicitly; unavailable values stay blank rather than becoming zero.
- Users can show all rows, recorded discrepancies or unavailable comparisons without changing
  the accounting run. General comparison notes remain visible when filtering. Older details
  without recorded results are not inferred to pass from their displayed amounts.
- Targeted viewer checks exercise offsetting aggregate differences, filters, missing amounts,
  source links and retained notes; TypeScript and scoped lint pass. Direct main publication;
  no deployment or accounting-calculation change.
- Combined-contract aging needs a presentation decision: retain original payer-owned layers with
  a separate member-allocation adjustment, or apportion original dated layers on the existing
  member liability basis. Current engine member totals alone do not specify that date ownership.
  The question has been raised with the owner; no new allocation rule is silently assumed.

## Historical GL source identity — October 20, 2026

- Fixed a historical comparison defect: filtering updated_at before selecting the latest GL
  reconciliation could skip a later-reopened source and falsely PASS against an older reviewed
  source. New v4 runs select the latest eligible identity first; a later mutation now records
  NOT_APPLICABLE with its source link and a historical-evidence reason, without future totals
  or future review status. No older source is substituted.
- Previously retained v1/v2 arithmetic and v3 reviewed-source evidence keep their original
  controls. Accepted and unavailable v4 runs also reproduce from their retained evidence.
- Public API checks create two independently reviewed GL sources, then reopen the latest after
  the cutoff. Both balance reports refuse the stale fallback; earlier accepted runs and new
  unavailable runs rerun identically. The existing review workflow and 12 scoped control cases
  pass, with lint/types and migration 0235 down/up catalogue parity. No deployment.
- This does not reconstruct mutable reconciliation history that was never retained. Combined
  member-aging date ownership, independent accounting sign-off and final-candidate checks remain.

## RPO first-batch modification attribution — October 20, 2026

- Stage 06 now retains fixed-allocation before/after amounts and signed changes for every
  obligation present at each modification boundary, including explicit zero changes. The new
  nodes re-evaluate from the retained engine state; accounting postings are unchanged.
- RPO first-entry batches separate later modifications and estimate changes from NEW_CONTRACTS
  when original event evidence is complete. Within one retained version, monthly modification
  and estimate movements must reconcile together to the dated fixed-allocation difference.
  Earlier months exclude future changes. Invalid boundary evidence is rejected.
- Targeted engine/report checks cover a native price-only modification followed by estimate
  increases and decreases, first-entry and monthly views, original-node replay and invalid
  evidence. Existing same-date/prospective modification checks and the public K01 period
  rollforward pass. Lint/types and migration 0236 down/up catalogue parity pass. No deployment.
- Old traces are not backfilled. Missing modification boundaries, newly introduced obligations
  lacking a complete boundary history and cancellation mixtures retain existing limitations.
  Combined-member aging date ownership and independent accounting sign-off remain open.

## RPO obligations added to existing contracts — October 20, 2026

- Fixed a classification defect: an obligation absent from the opening version was always
  treated as NEW_CONTRACTS, even when an already disclosed contract added it by amendment.
  Added obligations now follow the modification/estimate causes of that existing contract.
  First admission and cancellation re-entry keep their admission semantics; ambiguous mixed
  changes without original estimate shares remain unexplained rather than becoming new contracts.
- New report bindings retain rpo_added_obligations_v1. Earlier bindings preserve their original
  classification on rerun; the same selected semantics feed converted monthly rollforwards.
- The public Marrowby approval journey adds O2 and redistributes O1: all 60,000 is MODIFICATIONS,
  NEW_CONTRACTS and UNEXPLAINED are zero, and all ties pass in transaction, functional and
  reporting views with identical reruns (USD in each view). The 38 scoped report cases cover
  mixed additions, legacy behavior, entry/re-entry and exemptions; lint/types and migration
  0237 down/up catalogue parity pass. No deployment; publish directly to main.
- This does not supply missing first-batch boundary history, resolve combined-member aging date
  ownership or provide independent accounting sign-off. Those remain outstanding.

## Monthly RPO exemption translation details — October 20, 2026

- Converted rollforwards now retain each nonzero contract-period exemption movement in its
  original currency and the exact translated amount already used by the report. This explains
  nonzero translated flows even when the full-range original exclusions cancel at the endpoints.
  Existing obligation endpoint details remain separate; no allocation or FX math is done in UI.
- The viewer displays the monthly bridge even with no endpoint detail rows. Excel exports
  numeric source/translated cells with guarded identities; PDF exports readable period and
  currency amounts; CSV manifests retain the structured records. New bindings record
  rpo_exemption_translation_v1 and older bindings keep their existing control shape.
- Focused witnesses cover EUR-to-USD and EUR-to-USD-to-GBP: opposite original 100 movements at
  different monthly rates produce net 20 USD / 16 GBP, matching EXEMPTIONS with separate FX and
  zero rounding. Export, viewer, scoped types/lint, public report reruns and migration 0238
  catalogue parity are the necessary checks. No deployment; direct main publication.
- Combined-member aging date ownership, missing first-batch boundary histories, independent
  accounting sign-off and final-candidate verification remain outstanding.

## First-batch RPO creation boundaries — October 20, 2026

- Stage 06 records whether the obligation existed before each boundary and the original
  event record sequence. For an obligation added after earlier modifications, RPO can now prove
  those earlier subject boundaries are legitimately absent instead of requiring nonexistent rows.
  Earlier event order must still be retained on another obligation in that same computation.
- A zero before amount alone is not absence evidence. Missing creation or earlier event order,
  multiple creation histories and missing post-creation boundaries keep the conservative fallback.
  Legacy traces are not backfilled; original accounting amounts and event order are unchanged.
- Full compute witnesses combine a price decrease, an addition later on the SAME day and a
  subsequent estimate increase/decrease in one first computation. New contracts, modifications,
  estimates and historical/monthly cuts reconcile, and the new trace nodes re-evaluate. The
  40 scoped report cases and public modification/report journey pass, including three currency
  views and reruns. Lint/types and migration 0239 down/up catalogue parity pass. No deployment.
- Combined-member aging date ownership, legacy evidence gaps, cancellation mixtures, independent
  accounting sign-off and final-candidate verification remain outstanding.

## Source-reconciled mixed RPO cancellations — October 20, 2026

- RPO can now separate modification and original estimate changes from a single terminal
  cancellation in a later retained version. Admission requires opening fixed allocation plus
  those original deltas to equal the trace's amount immediately before termination. A residual
  is not used as evidence. Cancellation still removes only unrecognized allocation; current
  revenue and prior-period revenue restatements retain their own lines.
- Cancellation identities and original before/after boundary amounts are loaded explicitly.
  New bindings use rpo_cancelled_changes_v1; older bindings retain their former classification,
  including in converted monthly rollforwards. No engine posting change.
- Full-compute concession/estimate/termination traces prove the pre-termination bridge for both
  estimate directions; mismatched starting amounts are refused. The 48 scoped cases include
  recognized/reversed/restated revenue, realized consideration, missing bridges and legacy
  behavior. Existing public modification reports and reruns in three views pass. Lint/types
  and migration 0240 down/up catalogue parity pass. No deployment; direct main publication.
- First-entry-and-cancel batches, multiple cancellations, usage-event mixtures and estimates
  on the termination day remain unsupported by this decomposition. Combined-member aging date
  ownership, independent accounting sign-off and final-candidate verification also remain open.

## Same-day estimate and cancellation ordering — October 20, 2026

- RPO now loads the immutable contract-event record sequence for estimate causes, using the
  same (effective date, record sequence, event key) order as the engine. A same-day estimate
  before the original termination can participate in the reconciled cancellation bridge;
  missing order or an estimate at/after termination remains unsupported.
- New bindings retain rpo_cancelled_changes_v2. Existing v1 runs keep their date-only rule and
  retain v1 again on rerun; older runs without cancellation decomposition remain unchanged.
  No event is reordered and no engine accounting amount changes.
- Full-compute positive/negative estimate cases now cover same-day termination, missing order,
  reversed order and v1 behavior. The eight targeted first-batch cases, public modification
  reports/reruns in three views, lint/types and migration 0241 down/up catalogue parity pass.
  No deployment; direct main publication.
- First-entry cancellation batches, multiple cancellations, usage mixtures, combined-member
  aging ownership, independent accounting sign-off and final-candidate checks remain open.

## Original cancellation dates preserve historical RPO — October 20, 2026

- Stage 06 retains each obligation's original termination date and pre-boundary end date.
  Historical RPO and close-variance reads now preserve the pre-cancellation remainder;
  cancellation no longer removes that obligation from earlier months. New trace evidence
  drives the change; old computations without those dates keep their former behavior.
- A fixed-only first computation containing entry, modification, estimate change and one
  later cancellation can separate those movements, recognized revenue and cancelled remainder.
  Same-version subsequent-month rollforwards reconcile original deltas to the termination
  boundary. Later/missing event order and realized-usage mixtures are not inferred.
- Full engine witnesses cover positive/negative estimates, same-day ordered termination,
  refund/non-refund cancellation, historical standalone RPO/variance and monthly rollforwards.
  All 50 scoped cases and existing public modification reports/reruns in three currency views
  pass. Scoped lint/types and migration 0242 down/up IPE parity pass. No deployment.
- Multiple cancellations, first-entry cancellation followed by another retained version in the
  same range, same-day entry/cancellation, realized-usage mixtures and combined-member aging
  ownership remain open. Independent accounting sign-off and final-candidate checks remain open.

## RPO cancellations survive later retained versions — October 20, 2026

- A first-batch cancellation is settled before a later retained version supersedes its
  revenue evidence. The same bridge now handles an opening obligation cancelled before the
  next retained version. Later cancelled versions carry retained revenue; re-entry admits
  only its remaining allocation, preserving the earlier cancellation and revenue lines.
- New report bindings retain rpo_cancelled_chains_v1; existing bindings keep the prior
  classification on rerun. The change also reaches monthly converted rollforwards through
  the shared Store. Accounting computations and original events are unchanged.
- The 50 scoped cases pass, including real-engine cancellation traces adapted into later
  retained/memo and re-entry chains, both estimate directions, refunds/non-refunds, full-range
  and monthly balances, and legacy behavior. Existing public modification reports/reruns in
  three views, scoped lint/types and migration 0243 down/up catalogue parity pass.
- Multiple cancellations within one computation, versions intervening before the original
  termination, same-day entry/cancellation, usage mixtures and combined-member aging ownership
  remain open. Independent accounting sign-off and final-candidate checks remain open.
  Direct main publication; no deployment.

## Terminal realized usage stays out of fixed cancellation attribution — October 20, 2026

- For an opening obligation and one later terminating version, the report now uses the
  terminating version's dated realized amount when both versions retain realization evidence.
  Newly realized fees and signed corrections remain VC changes, rather than distorting the
  cancelled remainder. Mixed modification/estimate attribution still requires the original
  fixed pre-termination bridge; missing realization evidence preserves unexplained differences.
- New bindings retain rpo_cancelled_usage_v1; older bindings preserve former classification.
  The shared reader covers transaction and monthly converted rollforwards. No engine postings
  or original usage events change.
- Fifty-eight scoped report cases plus six engine realization cases pass. New reader cases
  cover positive/negative/zero fee changes, revenue restatement/reversal, missing evidence and
  legacy behavior. Existing public modification reports/reruns in three views, lint/types and
  migration 0244 down/up IPE parity pass. No new public usage/termination journey is claimed.
- First-entry/same-version usage cancellation, multi-version usage chains, multiple cancellations
  inside one computation, intervening pre-termination versions and combined-member aging policy
  remain open, alongside independent accounting sign-off and final-candidate verification.
  Direct main publication; no deployment.

## First-batch and same-version realized-fee cancellation — October 20, 2026

- A single first-entry cancellation computation and an opening-to-closing cancellation within
  one retained version now separate original realized fees. VC carries the realized change;
  cancellation removes fixed plus realized allocation net of recognized revenue. Original
  fixed modification/estimate bridges and dated realization evidence remain required.
- New bindings use rpo_cancelled_usage_v2. Retained v1 keeps its later-version-only behavior
  and retains v1 again on rerun. No event, accounting posting or stored amount changes.
- The 66 scoped report cases pass, including eight new reader cases for first entry versus
  monthly opening, realized increases/corrections, partial recognition and full reversal, plus
  legacy behavior. Existing public modification reports/reruns in three currency views,
  scoped lint/types and migration 0245 down/up IPE parity pass.
- New cases are report-reader witnesses, not a full-compute/API usage-plus-cancellation journey.
  Multi-version usage chains, multiple cancellations within a computation, intervening versions,
  same-day entry/cancellation and combined-member aging ownership remain open. Independent
  accounting sign-off and final-candidate verification remain open. Direct main; no deployment.

## Realized-fee cancellation follows continuously cancelled version chains — October 20, 2026

- A retained cancelled tail now supplies the final realized-fee amount only when every
  subsequent version remains included/cancelled and retains dated realization evidence.
  First-batch, same-version opening and later-version cancellation bridges can use that final
  source; recognized revenue also follows the retained final version. Original fixed changes
  remain tied to their termination boundary, with no new source amounts invented.
- New bindings use rpo_cancelled_usage_v3. Existing v1/v2 runs retain their prior feature scope
  and marker on rerun. Chains with re-entry, missing obligations, excluded versions or missing
  realization evidence are not admitted by the new tail reader.
- All 66 scoped cases pass, now including signed later fee corrections against first-entry,
  monthly opening and later-version cancellations, legacy classification and absent evidence.
  Existing public modification reports/reruns in three views, lint/types and migration 0246
  down/up IPE parity pass. New chain witnesses adapt retained report data, not public API events.
- Usage chains with re-entry, multiple cancellations within one computation, intervening
  pre-termination versions, same-day entry/cancellation and combined-member aging ownership
  remain open. Independent sign-off and final-candidate verification remain open. No deployment.

## Realized fees follow cancellation and re-entry segments — October 20, 2026

- For separately retained cancellation/re-entry versions, realized fees now use the final
  cancellation evidence up to the next re-entry cut. Re-entry admits fixed plus realized
  allocation net of pre-entry revenue, and pre-entry realized fees are removed from in-scope
  VC changes. This repairs misclassification that could previously balance in total while
  understating NEW_CONTRACTS and overstating VC_ESTIMATE_CHANGES.
- New bindings use rpo_cancelled_usage_v4; retained v1-v3 keep their feature scope and markers.
  Excluded/missing obligations or absent realization evidence do not authorize the segment read.
  Original fixed allocation and revenue traces remain unchanged.
- All 70 scoped cases pass, including usage fees through one/repeated cancellation and re-entry,
  reports beginning before/after cancellation, line-level expected amounts and legacy behavior.
  Existing public modification reports/reruns in three views, lint/types and migration 0247
  down/up IPE parity pass. New re-entry cases are retained-reader witnesses, not API journeys.
- First-batch/same-version usage cancellation followed by re-entry, multiple cancellations in one
  computation, versions intervening before termination, same-day entry/cancellation and combined-
  member aging ownership remain open. Independent sign-off/final-candidate checks remain open.
  Direct main publication; no deployment.

## First-batch realized-fee cancellation settles before re-entry — October 20, 2026

- An original cancellation embedded in the first/opening computation can now settle its dated
  realized fees at the next retained re-entry. Intermediate cancelled corrections supply the
  final evidence for that segment; fees are settled once before admission of the new remainder.
  The fixed allocation bridge and retained revenue recognition remain separate.
- New bindings use rpo_cancelled_usage_v5. Retained v1-v4 preserve scope and markers on rerun.
  Missing realized evidence, missing obligations or excluded intermediate versions still cannot
  authorize the new segment reader. Original accounting amounts and events are unchanged.
- The 70 scoped report cases cover direct and intermediate-correction re-entry after first-batch
  or same-version monthly cancellation, positive/negative realized changes, revenue reversals,
  line-level expected results and legacy behavior. Existing public modification reports/reruns
  in three views, scoped lint/types and migration 0248 down/up IPE parity are the release checks.
  New combinations use retained-reader witnesses, not a new public API lifecycle journey.
- Multiple cancellations within one computation, intervening pre-termination versions, same-day
  entry/cancellation and combined-member aging ownership remain open. Independent accounting
  sign-off and final-candidate verification remain open. Direct main; no deployment.

## Reviewable monthly unexplained RPO differences — October 20, 2026

- Confirmed all 59 catalogue definitions have registered execution paths. Converted RPO
  rollforwards now retain every nonzero source contract/entity/period difference with its
  original amount and the exact translated amount already used by the report. Offsetting
  months or rounding to zero no longer hide why the existing source tie-out failed.
- The report viewer and run record show an open detail table; XLSX/PDF render readable rows
  and the CSV manifest retains the same facts. Currency registration now includes currencies
  present only in retained RPO/exemption details. No UI allocation, FX or root-cause inference.
- New bindings retain rpo_unexplained_details_v1; older runs keep their original control totals.
  Functional/reporting offset cases, viewer display, formula-safe numeric XLSX/PDF/manifest
  exports, existing public three-view reports/reruns, lint/types and migration 0249 parity pass.
- This identifies source differences; it does not repair unsupported attribution combinations.
  Multiple cancellations within one computation, intervening pre-termination versions, same-day
  entry/cancellation and combined-member aging ownership remain open. Independent accounting
  sign-off and final-candidate checks remain open. Direct main publication; no deployment.

## Same-day fixed activation and cancellation retain gross movements — October 20, 2026

- A single first computation with same-day activation and cancellation can now retain the
  original fixed allocation as NEW_CONTRACTS, original recognized revenue and the cancelled
  remainder, instead of omitting every movement because closing status is CANCELLED.
  Original termination date/before allocation and explicit zero realized evidence are required.
  Booked/activation/termination/memo causes are admitted; other event mixtures remain outside
  this path. Full exemptions still omit the movement; closing disclosure remains zero.
- New bindings retain rpo_same_day_entry_cancel_v1; earlier runs preserve their classification.
- Full engine refund/non-refund witnesses use actual dated trace reads and all original event
  causes. The 72 scoped cases, existing public three-view reports/reruns, lint/types and
  migration 0250 down/up IPE parity pass. The new engine cases are not a new API lifecycle test.
- Same-day modification/estimate/usage mixtures, multiple cancellations in one computation,
  intervening pre-termination versions and combined-member aging ownership remain open.
  Independent accounting sign-off and final-candidate checks remain open. No deployment.

## Separate obligations can cancel in one retained computation — October 20, 2026

- Mixed cancellation attribution now selects the original cancellation of each obligation,
  rather than rejecting every contract with multiple termination causes. Each termination
  must retain explicit per-obligation state, exactly one must cancel that obligation, and
  every other termination must have zero fixed-allocation effect on it. The existing original
  opening/modification/estimate bridge still must reconcile; missing or cross-affected evidence
  remains unsupported. New bindings use rpo_separate_cancellations_v1; legacy rules are retained.
- A full engine case now applies a concession and estimate change, partially terminates A,
  then terminates B with two refunds. First-batch/monthly reporting and the later retained
  version bridge reconcile; legacy, missing metadata and nonzero cross-effects are checked.
- The 72 scoped cases, targeted negative checks, existing public three-view reports/reruns,
  lint/types and migration 0251 down/up IPE parity pass. New split-cancellation evidence is an
  engine/read-layer witness, not a new public API journey. No deployment; direct main.
- Cancellations with cross-obligation reallocations or repeated effects on one obligation,
  intervening pre-termination versions, complex same-day entry mixtures and combined-member
  aging ownership remain open. Independent accounting sign-off/final-candidate checks remain open.

## Partial cancellations attribute allocation effects on other obligations — October 20, 2026

- Original nonzero fixed-allocation changes from earlier partial terminations now enter
  CANCELLATIONS, including first-entry/monthly cuts and mixed later-version bridges. They no
  longer inflate NEW_CONTRACTS or prevent the original modification/estimate split. Explicit
  per-event state and unique actual cancellation are required; nonzero effects after that
  cancellation remain unsupported. Same-day cross-effects require original sequence evidence.
- New rpo_cancellation_cross_changes_v1 bindings preserve the expanded rule; older report runs
  retain their classification. Migration 0252 and catalogue describe the same evidence rule.
- A full engine witness pools B prospectively when cancelling A, then cancels B. Original dated
  trace reads verify full/monthly and later-version attribution, with legacy/refusal checks.
  73 scoped cases, existing public three-view report/rerun journey, lint/types and migration
  down/up exact IPE parity pass. The new lifecycle witness is not a new public API journey.
- Repeated cancellation/reentry mixtures, intervening pre-termination versions, complex same-day
  entry mixtures and combined-member aging ownership still need work. Independent accounting
  sign-off/final-candidate checks remain open. No deployment; publish directly to main.

## Partial-cancellation reporting works before the surviving obligation ends — October 20, 2026

- First-entry and same-version monthly RPO cuts now attribute original partial-termination
  allocation effects on still-disclosed obligations to CANCELLATIONS, and retain the separate
  modification/estimate movements. Original explicit state for every termination is required;
  monthly movements must match dated fixed allocations. New bindings retain
  rpo_continuing_cancellations_v1; older reports preserve their earlier attribution.
- Fixed the engine blocker revealed by the cross-month scenario: JET-06 cumulative reclass
  components have an immutable destination role, so their never-applicable zero-weight role
  shares no longer collide with another destination's real accumulated balance. Ordinary split
  targets still retain explicit zero shares needed to reverse prior nonzero contributions.
- The full-engine witness now covers both same-period and February/March partial/full
  cancellations. February opening/new/modification/estimate/cancellation/closing lines and March
  revenue/cancellation lines reconcile. Actual NETTING_RECLASS close-pass lines preserve CA 20
  reversal and UR 280 reclassification; this is not merely an endpoint-balance assertion.
- 77 scoped RPO/netting cases, the added close-pass witness, existing public three-view reports
  and reruns, lint/types, and migration 0253 down/up exact catalogue parity pass. New lifecycle
  evidence is engine/read-layer coverage, not a new public API lifecycle journey.
- Mixed later-version changes while an obligation remains active, intervening pre-termination
  versions, repeated cancellation/reentry and complex same-day entry still require completion.
  Combined-member aging ownership, independent sign-off and final-candidate checks remain open.
  No deployment; direct-main publication only.

## Mixed retained-version causes separate while obligations remain active — October 20, 2026

- A later retained version that combines modification, estimate and partial-termination causes
  now separates their original fixed amounts even when the affected obligation remains in RPO.
  Complete original modification/termination coverage and estimate shares/dates are required;
  their sum must equal the actual version movement. Missing evidence or mismatches remain
  unexplained. New bindings retain rpo_mixed_continuing_changes_v1; legacy attribution remains.
- The engine-generated cross-month partial-cancellation case now also feeds a prior January
  version and a later February version into reporting. The surviving obligation's modification
  and cancellation amounts complete the contract's separate February movement lines without
  waiting for its March cancellation. This is an adapted retained-version read-layer witness,
  not a new public API partial-termination lifecycle journey.
- All 74 scoped RPO cases, original close-pass witness, legacy/missing-source/mismatched-delta
  checks, existing public three-view reports/reruns, lint/types and migration 0254 down/up exact
  IPE parity pass. No deployment; commit directly to main.
- Intervening versions before original termination, repeated cancellation/reentry, complex
  same-day entry mixtures, combined-member aging ownership, independent accounting sign-off
  and final-candidate checks remain open. This is not a production-readiness claim.

## Transaction-currency RPO retains monthly unexplained differences — October 20, 2026

- Transaction-view RPO rollforwards now measure every selected period boundary and inspect
  original contract/entity/currency monthly differences. Opposite monthly gaps can no longer
  disappear behind a zero range total: any nonzero source gap fails the rollforward tie-out.
  Existing range rows stay intact and unexplained_details exposes each problem month in the
  viewer, XLSX/PDF and manifest, with unchanged original/report-currency amounts.
- New rpo_transaction_monthly_gaps_v1 bindings preserve the monthly rule and dated inputs on
  rerun; older transaction bindings retain prior range-only checks. Converted views retain
  their existing monthly checks. UI/export explanation now describes both source netting and
  currency rounding, and the viewer labels the second value as Report difference.
- A real builder/read-layer case has unsupported +10/-10 monthly changes and a zero net range:
  it fails with both details, reruns identically, and preserves the legacy pass. Supported
  modification movements still pass with no gaps. Scoped converted/exemption checks, existing
  viewer/export cases, the public three-view report/rerun journey, lint/types and migration
  0255 down/up exact catalogue parity pass. The gap case uses supplied retained version rows,
  not a new public API contract lifecycle journey.
- Complex cancellation/reentry and intervening pre-termination versions, same-day entry
  mixtures, combined-member aging ownership, independent accounting sign-off and final-candidate
  checks remain open. No deployment and no production-readiness claim; direct main only.

## Transaction-currency reports show intermediate monthly exemption movements — October 20, 2026

- Transaction-view RPO now retains nonzero contract/entity/period exemption movements even
  when the contract enters and leaves exemption within the range and endpoint details are
  empty. The shared exemption_translation schema stores unchanged original/report amounts;
  new bindings retain rpo_transaction_monthly_exemptions_v1 and old bindings keep prior detail
  populations. Existing range-level report rows are unchanged.
- Viewer and XLSX/PDF distinguish Monthly exemption movements from converted Monthly exemption
  translation, label unchanged amounts as Report movement and explain that intermediate
  monthly movements can differ from the range endpoint-based Exemptions line. Manifest controls
  retain the details with the original periods and currencies.
- The builder/read-layer right-to-invoice round trip retains EUR -110/+110 with no endpoint
  exclusions, passes reconciliation and reruns identically. Legacy omission is preserved.
  Five scoped builder/converted/export cases, both viewer currency modes, public three-view
  report/rerun journey, lint/types and migration 0256 down/up exact catalogue parity pass.
  New monthly witness uses supplied retained rows, not a new public contract lifecycle journey.
- Complex cancellation/reentry, intervening pre-termination versions and same-day entry mixtures,
  combined-member aging ownership, independent accounting sign-off and final-candidate checks
  remain open. No deployment; direct-main publication; no production-readiness claim.

## Historical GL reports retain original review state and amounts — October 20, 2026

- GL bridge v5 reads database-captured immutable GL reconciliation revisions at the report
  cutoff, retaining the chosen source's original status, totals, attachment and revision ID.
  A later reopen or update no longer erases covered historical comparison evidence. The current
  reopened source remains unavailable; older v1-v4 report bindings keep their original rules.
- Migration 0257 extends the existing tenant/entity-scoped report_source_revision mechanism.
  Source triggers capture inserts/updates, validate the original row and assign the revision
  time/sequence. Baselines attest only to migration-time state; absent older coverage remains
  unavailable. Downgrade refuses to discard captured GL history. No permission scope is widened.
- The real GL command journey generates/attaches a trial balance, explains and signs it,
  then reopens it. Historical comparison and retained rerun preserve the reviewed amounts;
  current comparison is unavailable. Original unattached state remains unavailable, and a direct
  application insert of an otherwise identical revision is rejected by the database guard.
- Viewer shows captured-state time; XLSX standalone/workbook exports retain revision identity
  and time, with PDF/manifest carrying the same detail fields. Thirteen GL control cases, the
  public review/reopen journey, two workbook cases, viewer/types/lint and exact IPE catalogue
  parity pass. Evidence-preserving downgrade refusal was checked in a rolled-back transaction.
- This supersedes v4's changed-after-cutoff limitation only where captured history exists.
  Concurrent commit-time visibility remains the separate B4-11 gap; this sequential workflow
  does not prove that guarantee. RPO complex lifecycle gaps, combined-member aging ownership,
  independent accounting sign-off and final-candidate checks remain open. No deployment;
  direct-main publication and no production-readiness claim.

## Retained RPO FX evidence is readable in viewers and exports — October 20, 2026

- RPO and RPO rollforward viewers now expose retained exchange-rate legs by entity,
  period, source/target currency and average/closing basis, with original rate IDs,
  rate-set versions and knowledge cutoffs. Exact rate strings are not money-rounded.
- Standalone and packed XLSX exports present the same retained legs as structured tables;
  PDF includes labeled rate details. Excel stores rates as text to preserve decimal precision.
  Unknown legacy export shapes retain their generic control presentation. No new FX reads,
  accounting calculations, binding changes or database migration are introduced.
- Two viewer cases and two export cases pass, including 18-decimal precision, original
  version identity, same-currency legs and spreadsheet formula escaping. Scoped lint and
  backend/frontend type checks pass.
- Complex RPO lifecycle attribution, B4-11 concurrent commit visibility, combined-member
  aging ownership, independent accounting sign-off and final-candidate checks remain open.
  This presentation improvement does not close those gaps. Direct main; no deployment.

## Same-day RPO entry/cancellation survives later versions — October 20, 2026

- RPO rollforward now preserves the original gross entry, revenue and cancellation when a
  fixed contract activates and terminates on the same day and later retained versions exist.
  Previously the single-version gate could silently omit all three movements despite a zero
  closing balance. Later memo versions retain the original movements; later disclosure re-entry
  adds only the remaining balance and does not recognize the earlier revenue twice.
- New bindings retain rpo_same_day_entry_chains_v1; legacy bindings keep the single-version
  eligibility. Original dated termination/realization requirements and competing-cause guards
  remain in force. Migration 0258 records the rule in the report IPE catalogue.
- Original engine termination witnesses with zero/40 refunds cover later memo and re-entry
  read-layer versions, legacy behavior and absent boundary evidence. The 74-case related suite
  had 73 passes and one overly broad legacy assertion; corrected scoped cases pass. Public
  currency report/retained-rate rerun, lint/types and migration down/up exact catalogue parity
  pass. Later versions are supplied read-layer witnesses, not new public lifecycle commands.
- Intervening versions before termination, mixed same-day entry causes, broader repeated
  cancellation/re-entry, B4-11 concurrent commit visibility, combined-member aging ownership,
  independent accounting sign-off and final-candidate checks remain open. No deployment.

## RPO pre-termination version attribution and requested pause — October 20, 2026

- RPO rollforward carries original pre-termination fixed balances across intervening
  retained versions. It no longer settles a future cancellation early or loses the original
  modifications, estimates and cancellation when a memo version precedes termination.
  A superseding computation determines the pending termination. Competing original modification,
  estimate and partial-cancellation amounts are separated before the pending cancellation settles.
- New bindings retain rpo_pretermination_versions_v1; older bindings preserve prior behavior.
  Original boundary coverage, chronology, fixed amount reconciliation and dated realization
  guards remain required. Migration 0259 records the rule in the IPE catalogue.
- All 74 related cases pass, including original engine termination amounts with intervening
  read-layer memo versions, mixed later-version causes, monthly/range cuts and legacy behavior.
  Public currency report/retained-rate rerun, scoped lint/types and migration downgrade/upgrade
  exact catalogue parity pass. Adapted version chains are not new public lifecycle witnesses.
- Remaining work includes broader repeated cancellation/re-entry and mixed same-day entry,
  B4-11 concurrent commit visibility, independent accounting sign-off and final-candidate checks.
  This does not establish production readiness. Direct main; no deployment.
- Owner decision, October 20: combined-contract aging must retain the original receiving
  contract's aging and show member allocation adjustments separately. The policy question is
  resolved; implementation remains outstanding. After this current RPO fix is published,
  pause development as requested; do not start the aging implementation until resumed.

## Original-owner aging and separate member allocations — October 21, 2026

- Implemented aging_member_adjustments_v1: original liability buckets retain their receiving
  contract and date; a separate Member allocation adjustment column bridges to the member's
  presented balance. Allocation adjustments have no invented age. Original owners remain
  visible even when their adjusted balance is zero, and group adjustment totals conserve cash
  layer balances. Complete retained engine member populations are required; unsupported or
  missing evidence is not silently repaired. Reporting translation preserves buckets and the
  adjusted total; retained legacy bindings keep their earlier schema.
- Re-lock comparisons treat allocation_adjustment as a monetary measure. Migration 0260 adds
  the IPE explanation. Targeted aging and re-lock checks, the platform historical-aging journey,
  the public functional/reporting aging rerun, lint/types and reversible migration catalogue
  parity passed. The combined-owner witness exercises retained-row/trace inputs; a full combined
  contract command-to-lock journey remains to verify before claiming all scenarios covered.
- Development scope is now public repository completion, not production readiness. Migration
  promotion, complete approval coverage, sandbox lock-chain reproduction and independent
  accounting sign-off are not completion gates. Sandbox refresh/isolation and key financial
  controls remain in scope. Preserve noncommercial licensing/publication exclusions; no deployment.

## Member aging adjustments agree with original engine amounts — October 21, 2026

- Combined-member aging adjustments now require each presented member amount to equal its
  retained original engine target, beyond complete membership and conserving the group total.
  Functional amounts require the exact member/period functional target in the requested currency.
  Missing, ambiguous, non-finite, wrong-currency or mismatched targets are refused, rather than
  treating a zero aggregate difference as evidence for an arbitrary member transfer.
- Original-owner age buckets and the separate adjustment column remain unchanged for valid
  sources. Focused cases cover offsetting member drift, a fully transferred zero-net owner,
  original functional targets and reporting translation; ten aging cases plus lint/types pass.
  No migration/schema change; no new full combined-contract command-to-lock claim.
- Continue the October 21 public-repository scope. No deployment, no independent accounting
  sign-off gate, no migration-to-live or sandbox lock-chain requirement.

## Combined aging public command/report/rerun path — October 21, 2026

- The combined aging feature now has a real command-to-report witness: two seat contracts
  are activated and combined through the approved public route, each receives a distinct billing
  event, and the combined group is computed by the production engine. Both original owners
  remain in the liability aging output with nonzero offsetting allocation adjustments.
- The report reconciles every member, and original buckets plus adjustment equal each presented
  balance. Public report creation and the worker return exactly the builder rows; the public
  retained rerun reproduces those rows and the Member allocation adjustment column header.
- The targeted database journey and lint pass. This closes the missing transaction-currency
  command-to-report witness; earlier scoped functional/reporting evidence remains as recorded.
  No deployment or additional production-readiness gate is introduced.

## Original same-day RPO entry amendments — October 21, 2026

- RPO now separates original amendments after same-day activation and before termination:
  an original 100 contract followed by a -20 amendment retains NEW_CONTRACTS 100 and
  MODIFICATIONS -20, alongside the original revenue and refund/cancellation amounts.
  Previously the mixed cause set suppressed the original entry entirely.
- The reader retains admission record sequence from the original bound cause events. Complete
  amendment boundaries, strictly ordered original records and continuity into termination's
  before-state are required. Later memo/re-entry versions do not count the amendment again.
  New bindings retain rpo_same_day_entry_modifications_v1; legacy eligibility is unchanged.
  Migration 0261 adds the IPE rule.
- All 76 related cases pass; targeted missing/contradictory admission-order checks also pass.
  The witnesses use original engine amendment/termination calculations with supplied retained
  report versions. Public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass; no claim of a new public same-day contract command journey.
- Same-day mixtures involving estimates/usage and broader repeated cancellation/re-entry remain
  open, as does concurrent commit visibility. Continue the October 21 repository-only scope;
  no deployment or independent accounting sign-off gate.

## Original inception estimates in same-day RPO entry — October 21, 2026

- Same-day activation/termination now retains initial variable consideration in NEW_CONTRACTS
  when every original estimate has an INCEPTION pin and an admission-date event. The engine
  treats inception-date versions as initial price regardless of same-day record order; the report
  follows that rule rather than inventing a routed estimate delta. Amendments and refunds remain
  separately attributed, including through later retained memo/re-entry versions.
- Missing original pins preserve prior eligibility. New bindings retain
  rpo_same_day_entry_estimates_v1; legacy bindings retain their old behavior. Migration 0262
  adds the matching IPE note. The reader loads the pins from original retained engine traces.
- All 80 related cases, public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass. Original-engine scenarios cover estimates before and after activation,
  optional amendments, refunds, later versions and missing evidence. These use supplied report
  versions; no new public same-day contract-command journey is claimed.
- Same-day usage mixtures, broader repeated cancellation/re-entry and concurrent commit visibility
  remain open. The October 21 repository-only scope continues; no deployment.

## Same-day RPO entry with realized usage — October 21, 2026

- Same-day activation/termination can now retain gross new-contract amounts when usage is
  present. Original termination before-state and traced realized fees are required; fixed entry,
  original amendments, usage changes, recognition and cancellation remain distinct movements.
  Later retained usage corrections adjust VC and cancellation without repeating entry/amendments.
- New bindings retain rpo_same_day_entry_usage_v1 and require the existing batch cancelled-usage
  decomposition. Missing realized evidence and older bindings preserve previous eligibility.
  Migration 0263 records the matching IPE rule.
- All 88 related cases, public currency/rate rerun, scoped lint/types and reversible migration
  catalogue parity pass. The new same-day usage/mixed-amendment and retained-correction witnesses
  use supplied boundary/cut evidence, not a new original-engine/public-command usage journey.
- Original-engine/public-command coverage for these same-day usage mixtures remains outstanding,
  along with broader repeated cancellation/re-entry and concurrent commit visibility. Continue
  the October 21 repository-only scope; no deployment or independent accounting review gate.

## Public termination controls and same-day usage calculations — October 21, 2026

- The modification form/API now accepts explicit FULL/PARTIAL termination scope and a refund
  in contract currency. Preview and approval use the same CONTRACT_TERMINATED event; the terms
  are stored, displayed in the detail, included in the approval fingerprint and cleared when
  switching to another modification kind. REMOVE lines must have non-positive deltas and cover
  the refund. New/edited termination drafts require terms; already approved historical rows
  without terms retain their original amendment semantics and hash. Migration 0264 retains
  the terms and refuses downgrade while any remain.
- The real command journey exposed two engine faults: inception-day realized fees were included
  in FIXED allocation and then counted again as period fees; an inception-day termination tried
  to extend recognition through a truncated segment ending before the first calendar period.
  Inception allocation now excludes separately recognized period fees, preserving zero trace
  nodes and contract-wide royalty-estimate allocation. Only later term ends extend the horizon.
- Four public journeys exercise two usage obligations, FULL/PARTIAL scope and refunds 0/40,
  including original engine calculations, required approval steps, contract status, reporting and
  retained reruns. Entry 160,000 and VC 150 remain separate; FULL recognizes the nonrefundable
  pool at termination, PARTIAL allocates it to continuing O2 and recognizes it over its term.
  Revenue, refunds and closing RPO reconcile. This closes the supplied-evidence-only limitation
  for this same-day usage/termination case, not every mixed amendment or re-entry sequence.
- Necessary checks pass: four public journeys, three ordinary modification regressions, 236
  pricing/allocation/recognition cases, 48 modification units, 88 RPO cases, 68 frontend cases,
  scoped lint/types, generated API parity, and migration round-trip/data-retention guard.
  Broader repeated cancellation/re-entry, combined same-day amendment/estimate/usage journeys
  and concurrent commit visibility remain open. No deployment.

## GL source selection uses one database snapshot — October 21, 2026

- GL comparisons now resolve source identities, latest captured states, review status and totals
  from immutable report_source_revision rows in one SQL statement across all requested entities.
  The previous current-header query followed by a separate revision query could mix snapshots
  when an already-inserted source revision committed between those reads. Windowed selection
  preserves latest-source precedence and requires a source attachment known at the cutoff.
- New runs retain rollforward_gl_inputs_v6; v1-v5 bound comparisons still rebuild from their
  original evidence. Migration 0265 updates IPE for contract_balances and
  contract_balance_rollforward. Uncovered source history remains unavailable.
- A real two-transaction witness commits a change to a reopened reconciliation after the source
  statement executes: the comparison retains the pre-commit source revision, performs one source
  query and preserves the earlier reviewed historical/bound result. The public uploaded-GL
  report path, 14 GL cases, lint/types and reversible migration/catalogue parity pass.
- This establishes a consistent GL source-selection statement, not historical commit timestamps
  or a transaction-wide snapshot for every report source. B4-11 arbitrary historical commit
  visibility remains open, as do broader RPO mixed-lifecycle journeys. No deployment.

## Public same-day usage, estimate and price-change sequence — October 21, 2026

- Extended the public termination journey with an approved 200 bonus estimate and 100 price
  increase after 150 usage, all effective on inception day. The original 160,000 computation
  already exists: NEW_CONTRACTS stays 160,000, VC_ESTIMATE_CHANGES is 350, MODIFICATIONS is 100,
  and CANCELLATIONS is the negative refund. Full termination recognizes the remaining pool;
  partial termination reallocates fixed consideration to the continuing obligation.
- This checks sequential retained computations, public preparation/review/preview/application,
  report ties and bound reruns for FULL/PARTIAL and refunds 0/40. It does not prove one initial
  computation containing every event, or repeated termination/re-entry. No calculation change
  was needed for this sequence. All eight targeted journeys and scoped lint pass; broader
  lifecycle and B4-11 gaps remain open. No deployment.

## RPO contract eligibility changes — October 21, 2026

- New RPO runs show ELIGIBILITY_CHANGES separately from new contracts, legal termination and
  disclosure exemptions. A retained collectibility exit requires an original not-probable event
  in the selected book at the version date, unchanged fixed allocation and dated realization.
  Criteria-met re-entry carries the remaining balance, excluding already recognized revenue
  and fees from earlier excluded segments. Repeated supported exits/re-entry are handled; a
  first-ever criteria admission remains NEW_CONTRACTS.
- The original Step 1 engine journey exits with opening RPO 1,100 and re-enters with 900: the
  net eligibility movement is -200, with no new-contract or termination amount and no unexplained
  difference. Repeated segments, start-after-exit and realized fees have targeted witnesses;
  monthly functional/reporting translation uses each month's retained average rates.
- New bindings retain rpo_eligibility_changes_v1. Older bindings keep their original calculation
  and columns. Generic output rows/columns and re-lock comparison include the new monetary line;
  migration 0266 updates IPE. Targeted RPO checks, the public rollforward path, lint/types and
  reversible migration/catalogue parity pass.
- Fully terminated contracts cannot be reactivated by the product. Earlier supplied re-entry
  fixtures did not prove that workflow. Mixed eligibility exits with price/estimate changes,
  multiple transitions inside one initial computation and B4-11 commit visibility remain open.
  The new eligibility journey uses original engine outputs; a public reassessment-to-report
  journey is still unverified. No deployment.

## Public eligibility workflow and historical projection reads — October 21, 2026

- The public reviewed collectibility/re-entry journey exposed two implementation faults.
  Operational HOLD_APPLIED/HOLD_RELEASED dates could move a June business change into September;
  RPO now dates versions by their business causes, while retaining each original computation
  and its dated recognition/hold evidence. Hold-only versions inherit the prior business date.
  New runs bind rpo_operational_hold_dates_v1; older bindings retain their previous dates.
- Database trace reads omitted cut, period_key and reason even though the engine retained them.
  These parameters now reach the existing projection reader: historical fixed schedules can use
  their original period projections, and unavailable-projection reasons are not silently lost.
- The public journey reviews a not-probable assessment, appends the significant change and
  assessment, generates June RPO, then reviews probable collection, submits/approves criteria
  re-entry and generates July RPO. Eligibility movements reconcile; rerunning June after July
  preserves its original rows. This closes the public-workflow gap recorded in the 0266 note.
- Migration 0267 updates both RPO definitions; reversible migration/catalogue parity, 93 dated
  reader cases, scoped lint/types and the public journey pass. Mixed eligibility exits with
  amendments/estimates, multiple transitions in one initial computation and B4-11 commit
  visibility remain open. No deployment or expanded approval requirement.

## Mixed allocation changes at RPO eligibility exit — October 21, 2026

- Retained collectibility exits can now separate concurrent CONTRACT_AMENDED and
  ESTIMATE_CHANGED allocations from the eligibility movement. Original amendment boundaries
  and complete estimate-event shares must reconcile the fixed allocation change; events after
  the exit, missing evidence and competing unsupported causes retain their unresolved result.
  Dated realization stays in VC; the resulting remaining balance leaves through eligibility.
- Trace loading includes excluded eligibility versions with estimates even when there is no
  amendment or entry. New report runs retain rpo_mixed_eligibility_v1; older bound runs retain
  the previous classification. Migration 0268 documents the rule without changing report columns.
- Four original-engine journeys cover plain exit/re-entry, price modification, estimate change,
  and both together. Their separate movements reconcile to original revenue schedules and
  remaining allocation. Missing evidence and legacy behavior are checked. The public reviewed
  exit/re-entry report and bound rerun, scoped types/lint, and reversible migration/catalogue
  parity pass. Mixed-event public command batching is not yet independently verified.
- Multiple eligibility transitions within one initial computation and B4-11 arbitrary historical
  commit visibility remain open. This closes the supported retained mixed-exit decomposition,
  not every lifecycle combination. No deployment or additional accounting sign-off gate.

## Initial RPO eligibility timelines — October 21, 2026

- RPO and its rollforward now read original Step 1 status nodes, linked to dated immutable
  source events, when one initial computation contains eligibility-only entry/exit/re-entry.
  Timeline slices retain the original computation ID, allocation and recognition evidence.
  A report starting during an excluded interval recognizes later re-entry as eligibility,
  not a new contract; initial computations ending excluded retain their earlier admission.
- Stage 09 now retains original-cut deterministic schedules before later contract-status
  changes. Without these projections, an excluded final computation erased the future lines
  needed to report its earlier included opening. No proportional schedule reconstruction is
  used. Older traces lacking the required historical projection still refuse that read.
- New runs bind rpo_initial_eligibility_timeline_v1; old bound runs keep the previous timeline.
  Migration 0269 updates both RPO definitions. Original-engine witnesses cover whole-lifecycle,
  opening-included, opening-excluded and post-re-entry ranges, including a final excluded
  computation. The 42 scoped engine/chain/report cases, public sequential eligibility journey
  and retained rerun, lint/types and reversible migration/catalogue parity pass.
- Initial batches mixing these status transitions with monetary events remain unfinished.
  A public batch-to-report witness remains to verify; the public regression above is sequential.
  Arbitrary historical commit visibility (B4-11) also remains open. No deployment.

## Monetary events in initial eligibility batches — October 21, 2026

- Initial RPO eligibility timelines now retain dated amendment and estimate slices, using
  original event-specific allocation shares. Changes before exit are separately classified;
  changes while excluded are included in the remaining re-entry balance, not NEW_CONTRACTS
  or in-scope modification/VC lines. Original computation IDs and amounts remain unchanged.
- The dated reader now exposes the fixed-allocation measurement date separately from revenue.
  A frozen revenue target may be dated at the exit while allocation still measures month-end.
  Lifecycle cuts remove later same-period changes using complete original boundaries/shares,
  preventing an excluded-period amendment from being included in the earlier exit balance.
- Fixed an engine invariant failure on estimates during a Step 1 revenue freeze. Matching
  frozen before/after targets retain a zero catch-up with the freeze date and S02-R-05 guard;
  the new allocation remains available for subsequent re-entry. Other segment checks remain.
- New reports retain rpo_initial_monetary_timeline_v1; older bindings retain their prior
  timeline. Migration 0270 updates both RPO definitions. Eight original-engine scenarios cover
  price/estimate/both at exit and during exclusion, final included/excluded states and four
  report start positions. The 132 scoped engine/reader/report cases, public sequential
  eligibility/rerun regression, lint/types and reversible migration/catalogue parity pass.
- Initial usage/royalty batches, monetary changes after a same-day status transition, and
  multiple transitions on a monetary-event date still need ordered amount evidence. The public
  batch-to-report witness and B4-11 historical commit visibility remain open. No deployment.

## Original-date usage across initial eligibility batches — October 21, 2026

- Stage 09 now retains realized allocation at original contract-event dates for usage/royalty
  components, using the same realization calculation as its retained period/version amounts.
  A dedicated reader validates these dated trace values; missing dates are not inferred from
  month-end values. Recognition and realization remain distinct.
- Initial usage timelines now use these exact dates at admission, eligibility exit and re-entry.
  Fees realized before exit are VC movements; fees realized while excluded enter with the
  remaining re-entry balance. Old report bindings keep the previous timeline. Migration 0271
  adds rpo_initial_usage_timeline_v1 to both RPO definitions.
- Two original-engine usage journeys cover fees before exit and while excluded within the
  same month. Opening/closing, VC, eligibility and zero unexplained movement reconcile;
  missing original date evidence is refused. The 43 scoped usage/royalty/eligibility checks,
  public initial-usage and sequential eligibility/rerun regressions, lint/types and reversible
  migration/catalogue parity pass. The royalty checks cover the existing engine behavior,
  not a complete royalty eligibility journey.
- Same-day monetary events after a status transition, multiple transitions on a monetary date,
  the public mixed-batch witness, full royalty eligibility witness and B4-11 historical commit
  visibility remain open. No deployment.

## Ordered Step 1 recognition freezes — October 21, 2026

- The engine now preserves each actual Step 1 transition's original event order in its
  internal contract state, alongside the existing date history. Recognition at an event
  position observes only preceding status transitions. Once eligibility is lost, fixed,
  usage and royalty recognition freeze immediately before that status event, excluding
  later changes even when they share its date.
- Same-day post-exit estimates retain a zero catch-up with explicit frozen evidence; a later
  same-day criteria re-entry cannot retrospectively change that earlier estimate position.
  The newer allocation remains available when recognition resumes. Date-only legacy
  internal states preserve their earlier behavior. Book memo rebinding and original-cut
  manual projection snapshots retain/filter the corresponding ordered history.
- Four original-engine witnesses distinguish pre/post-exit usage, amendments and estimates
  and a later same-day re-entry. The 91 scoped recognition, eligibility, estimate and book
  checks pass, including existing memo reuse. Scoped lint/types pass. Public sequential
  eligibility/rerun regression also passes.
- This fixes the engine's frozen recognition semantics; Reporting still needs original
  event-position monetary evidence before enabling the currently refused same-day batches.
  Public mixed-batch and full royalty eligibility witnesses and B4-11 historical commit
  visibility remain open. No deployment, schema or expanded approval requirement.

## Original event-position amounts for RPO — October 21, 2026

- Stage 09 retains before/after fixed allocation, realized consideration and cumulative
  revenue at eligibility, amendment, estimate and usage events of collectibility histories.
  Each point carries the original event key, date, sequence and source role; its trace
  formula re-evaluates. The report reader rejects changed sources and incomplete triples.
- Realized royalties now measure the requested date/position independently of frozen
  recognition. A statement arriving after a same-day eligibility exit increases realized
  consideration without retrospectively increasing the frozen revenue target.
- The 34 scoped usage, royalty, eligibility and original-position checks pass; scoped
  lint/types pass. No schema or report catalogue change in this increment.
- Reporting does not yet consume these positions: enabling ordered initial-batch attribution
  and its bound-run compatibility remains next. Return-path positional allocations are
  intentionally absent until their rates/estimates support the same event cutoff; readers
  must not substitute date-end amounts. Public mixed-batch and full royalty lifecycle
  witnesses, plus B4-11 historical commit visibility, remain open. No deployment.

## Ordered initial-batch RPO attribution — October 21, 2026

- Reporting now consumes original event-position amounts for initial computations containing
  eligibility transitions and monetary events. It orders actual transitions, amendments,
  estimates and usage by original date/sequence/key, preserving one computation identity.
  Changes before exit are modification/VC movements; changes while excluded enter through
  the remaining re-entry balance. Multiple transitions on one date no longer require a
  date-end proxy. Revenue after re-entry uses its original event-position opening amount.
- Original position metadata is checked against immutable events. Required missing
  obligation positions refuse rather than use day-end amounts. Later retained computations
  load positional evidence for restated segment openings. Old traces retain supported older
  timeline behavior; old bound runs do not enable the new ordered-evidence feature.
- Migration 0272 records this interpretation for RPO and rollforward. Both catalogue
  definitions match migration upgrade/downgrade. Thirty scoped original-engine/report checks
  pass, including 12 same-day usage/estimate/amendment cases before/after exit, with/without
  re-entry. The public sequential collectibility/re-entry and bound rerun check passes;
  scoped lint/types pass. Changes publish directly to main; no deployment.
- Remaining: public initial mixed-batch end-to-end coverage, return-path positional
  rates/estimates (not substituted), full royalty eligibility lifecycle coverage, and B4-11
  arbitrary historical commit visibility. This increment does not claim repository completion.

## Return-path original event positions — October 21, 2026

- Return estimate pins now carry their original applying-event order from stage 04.
  Recognition selects both the estimate and the allocation unit rate at the requested
  event position. Actual returns after an estimate consume its remaining expected units,
  including later returns on the same date; stage 04 pricing and stage 09 recognition
  now use the same ordering rule.
- RPO event-position evidence now includes return-path net fixed allocations using that
  same cutoff for the segment rate, expected units and actual returns. A later estimate
  or price change cannot rewrite an earlier eligibility exit. Legacy internal pins
  without event-order metadata remain excluded from positional evidence.
- Seventy-seven scoped pricing, returns, disclosure and ordered-eligibility cases pass,
  including original pricing-to-recognition same-day return consumption, frozen recognition
  across later estimate/price changes, and positional trace re-evaluation. Scoped lint/types
  pass. No schema/catalogue change; existing bound runs retain their original trace.
- Still open: initial Reporting timelines that include actual return/delivery causes,
  public mixed-batch end-to-end coverage, full royalty eligibility lifecycle coverage and
  B4-11 arbitrary historical commit visibility. This fixes positional return amounts; it
  does not claim every return lifecycle is enabled in the report. No deployment.

## Performance events in initial RPO eligibility batches — October 21, 2026

- Ordered initial Reporting timelines now admit delivery, actual return, billing and credit
  events with original before/after monetary evidence. Performance-driven net allocation
  changes are VC movements while included; changes while excluded enter with the remaining
  re-entry balance. Retained evidence also separates return-window expiry before a later event
  from that event's own cause, and measures expiry after the final event through report end.
- Migration 0273 versions this interpretation for RPO/rollforward. Older bound runs retain
  their original timeline. Missing required performance positions cannot silently fall back
  to a date-only timeline that drops those events.
- Thirty-four scoped original-engine/report cases pass, including twelve actual-return and
  delivery cases spanning pre/post-exit events, excess/partial expected returns, and expiry
  before/after the eligibility boundary. All reconcile with zero unexplained movement.
  Public sequential eligibility/re-entry and bound rerun pass; both catalogue definitions
  match upgrade/downgrade; scoped lint/types pass. No deployment.
- Remaining work includes public initial mixed-batch end-to-end coverage, full royalty
  eligibility lifecycle coverage and B4-11 arbitrary historical commit visibility. Billing
  and credit event admission is implemented but has no dedicated new mixed-batch witness in
  this increment. This is feature progress, not a repository-completion claim.

## Royalty lifecycle and supported public workflow — October 21, 2026

- Four original-engine Reporting journeys verify minimum-guarantee netting, downward
  statement corrections, licence satisfaction before/after the eligibility boundary and
  same-day statements before/after exit. All movement lines reconcile; the fixture now reads
  the actual recognition method instead of labelling every obligation USAGE.
- The public workflow intentionally rejects a batch mixing Step 1 reassessments with manual
  usage (API-R-30). Verified rejection leaves computation count unchanged. The supported
  separate-review sequence accepts usage while excluded, restores eligibility and preserves
  the earlier bound report on rerun. Both existing and usage-bearing public variants pass.
- A single public manual batch is therefore not a missing UI feature to enable by weakening
  controls. Ordered initial historical computations remain covered at the original-engine
  and report-builder boundary; no claim is made about every history-import route.
- This increment closes the stated royalty guarantee/statement/satisfaction witness and
  clarifies the public mixed-batch limitation without changing production logic. Scoped lint
  passes. Next implementation focus is B4-11 arbitrary historical commit visibility;
  final-candidate checks below remain outstanding. No deployment.

## Historical ledger commit visibility — October 21, 2026

- Historical ledger readers now require the original PostgreSQL commit timestamp, closing
  the insertion-before-cutoff/commit-after-cutoff race. Commit evidence is queued with the
  seal and retained after commit. Database guards prevent caller-supplied timestamps and
  later changes; read-only historical queries can resolve pending evidence directly.
- Ten report definitions version this ledger interpretation. Older bound runs preserve
  their seal-time basis. Disaggregation catalogue metadata is also brought into agreement
  with its existing ledger and multi-currency implementation.
- PostgreSQL requires track_commit_timestamp=on before posting; Compose and the optional
  GCP configuration include it, and check_env --db checks it. Migration 0274 requires an
  empty posting-seal table and refuses populated ledgers rather than inventing old commits.
  This is a repository-development prerequisite, not a migration-to-live deliverable.
- Sandbox refresh regenerates commit evidence with its own derived postings. No production
  transaction IDs are copied into sandbox evidence. No sandbox lock requirement is added.
- Necessary verification covers concurrent late commits, immutable timestamps, pending
  evidence fallback/recovery, read-only access, historical/record basis and catalogue parity.
  Scoped lint/types and the affected configuration/catalogue/snapshot checks pass.
- Remaining B4-11 work: other historical sources and direct report-specific seal queries
  still need commit visibility. Post-commit hook failures leave recoverable pending rows;
  automatic retry/monitoring before PostgreSQL discards old transaction evidence remains
  to implement. Expired evidence is refused, never replaced with an estimated timestamp.
  This increment does not close all historical-source gaps. No deployment.

## Automatic commit-evidence recovery — October 21, 2026

- The existing minute worker sweep now retries pending posting commit evidence per tenant.
  Recovery uses short batches, row locks with SKIP LOCKED, and savepoints per posting.
  Keyset progression passes failed entries so they cannot starve later pending rows; each
  failed entry is retried on the next sweep. Successful batches commit independently.
- Immediate after-commit retention remains the normal path. Migration 0275 adds a partial
  pending-only index so routine recovery does not scan the full ledger. Recovery logs posting
  failures and per-tenant retained/failed totals. Tenant recovery failures do not stop the
  existing job sweep or the next tenant.
- Verified against PostgreSQL: an injected statement failure on the first pending posting
  rolls back only that posting, the next batch retains the second, the next sweep recovers
  the first, and another sweep is a no-op. Minute-sweep tenant isolation and normal historical
  cutoff behavior pass; scoped lint and types pass. No deployment.
- This closes automatic retry of failed post-commit retention. PostgreSQL evidence already
  discarded before a worker can recover it remains unavailable and is explicitly refused;
  there is no invented fallback timestamp. Other B4-11 historical-source readers remain open.

## Retained ledger source and incremental export windows — October 21, 2026

- New subledger extracts and bookings/billings/revenue ledger contributions exclude postings
  committed after known_at, even when their insertion and business record times precede it.
  Original commit timestamps travel with retained input rows and are checked on rebuild.
- New incremental subledger extracts use (known_since, known_at] in actual commit time.
  A posting still uncommitted at the previous cutoff therefore appears in the next export,
  including backdated business records. Existing export columns remain unchanged; old bound
  extracts keep their recorded_at interpretation and original retained inputs.
- Migration 0276 synchronizes both report definitions with this interpretation. Database
  catalogue parity, a real late-commit/next-window journey, old/new bound extract rebuilds,
  the public JSON/CSV extract controls and rerun, and retained BBR cutoff validation pass.
  Six focused BBR unit cases plus scoped lint/types pass. No deployment.
- B4-11 is still open for non-ledger inputs such as contract events, version availability,
  journal state and other report-specific readers. This increment fixes the ledger source
  populations above; it does not claim full cross-source historical snapshot reconstruction.

## Contract event and version commit visibility — October 21, 2026

- Original contract-event and computed-version transactions now have database-controlled
  commit evidence, queued atomically with each source and archived after ordinary writes.
  The minute worker also recovers pending source evidence in isolated keyset batches.
  Delegated SYSTEM activation units are covered by that durable recovery path; read-only
  queries can resolve the real timestamp before archival. Archived evidence is immutable.
- Shared historical version selection excludes late commits before choosing the latest
  candidate, retaining the preceding version correctly. RPO history and the touched history,
  book-bridge, prior-obligation, SSP/allocation, modification and estimate readers use the
  same cutoff protection. Explicitly bound original version identities remain compatible.
- New event/version extracts and BBR event inputs retain their actual commit timestamps.
  Incremental event/version exports use (known_since, known_at] in commit time, so backdated
  events and computations committed after a prior export are picked up in the next window.
  Published columns are unchanged; old bound extracts retain their original input basis.
- Migration 0277 adds tenant-isolated evidence, pending indexes and synchronized metadata
  for the affected report definitions. It requires empty contract-event/version tables,
  refusing existing history rather than fabricating timestamps. Sandbox evidence regenerates
  with its own copied/recomputed sources; no production transaction identity is reused.
- Verified a real append/recompute transaction committed after an independent cutoff: the
  prior version and RPO history remain selected, BBR excludes the late event, both next-window
  exports include the new data, and new/legacy bindings reproduce. Public event/version and
  three latest-version extracts, archive immutability, catalogue parity and snapshot inventory
  checks pass, with scoped lint/types. No deployment.
- B4-11 remains open for mutable journal/GL revisions, membership/configuration state and
  report-specific source readers not covered here (including full historical modification
  state). Commit evidence alone does not reconstruct prior values of mutable rows. The wider
  final-candidate verification list remains outstanding; independent accounting sign-off and
  migration-to-live work remain outside the owner's development scope.

## Committed GL and contract-source revisions — October 21, 2026

- Migration 0278 extends original transaction evidence to immutable report-source revisions
  (GL reconciliation state, contract headers and customer/entity code labels). Source triggers
  queue evidence atomically; the existing minute recovery archives it. Existing revision
  history is not assigned invented commits: upgrade requires an empty revision table, and
  retained revision-commit evidence prevents downgrade.
- GL bridge v7 filters revision commits before ranking source identity and review state in
  its single snapshot query. A change inserted before a report cutoff but committed afterward
  no longer replaces the original reviewed/reopened state on a later historical read.
  Revision identity, insertion time and actual commit time are retained. Bound v1-v6
  comparisons keep their original evidence and control rules.
- Contract exports resolve header and code-label revisions at committed cutoffs. New
  incremental exports return the latest contract when its header or customer/entity code
  changed in (known_since, known_at], covering updates and late commits as well as new rows.
  This remains an upsert dataset, not a deletion feed. Columns are unchanged; old bound
  extracts preserve their original creation-time interpretation and retained labels.
- Necessary checks pass: public reviewed GL/reopen flow with a real overlapping commit and
  subsequent historical replay, old-v6 GL binding, source-owned contract revisions, late
  header updates, code-only incremental changes, new/legacy extract bindings, archive guards
  and catalogue parity. Scoped lint/types pass. No deployment.
- Remaining historical work includes journal-run state and other mutable memberships,
  configuration and report-specific inputs. These changes cover retained GL and contract
  revisions; they do not claim arbitrary reconstruction for every mutable source.

## Committed journal lifecycle and line availability — October 21, 2026

- Migration 0279 captures immutable journal-run/batch revisions and original journal-line
  transaction evidence. Ordinary generation archives line commits after commit; the existing
  recovery worker also covers pending evidence. No invented history: upgrade requires empty
  journal tables, and retained new evidence prevents downgrade.
- Journal exports resolve lifecycle revisions by actual commit cutoff, so a cancellation
  inserted before cutoff but committed afterward cannot remove lines from the old report.
  Incremental exports use line commits in (known_since, known_at]; public columns stay fixed
  and older retained bindings preserve their original interpretation.
- Historical revenue waterfall/disaggregation journal comparisons use committed line
  populations and run state. BBR journal comparison inherits the export behavior. Production
  actuals captures consume resolved committed states without reinterpreting application clocks.
- Necessary checks passed: public JSON/CSV exports and retained reruns, real overlapping
  cancellation commits, incremental lines, historical/current journal totals, archive guards,
  catalogue parity, database architecture, focused actuals/catalogue/BBR units, lint/types.
- Remaining: JE Population complete retained inputs, sample journal evidence and other mutable
  report inputs/configuration still need work. This does not claim all historical sources are
  complete. No deployment or actual-business migration is required or performed.
