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
