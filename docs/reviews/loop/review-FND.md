# FND review: phase 01, items FND-1 to FND-18

| Field | Value |
|---|---|
| Reviewed commit | `374edb3` (FND-18), worktree `~/dev/erev-rv/fnd` |
| Main HEAD at synthesis | `9984d0d` (EKC-4). Among the cited paths, only `backend/tests/architecture/test_data_model_drift.py` changed after `374edb3`, so every finding below is still current |
| Date | 2026-09-12 |
| Inputs | Setup baseline; four lenses (conformance, security, gates, maintainability); two verifier passes per lens (reproduction and authority) |
| Remediation | `~/dev/erev-rv/reports/fnd/SUPERVISOR-ITEM.md`: SUP-FND-1, SUP-FND-2 and SUP-FND-3 |

## Result

**Phase FND meets its BUILD_SPEC acceptance, and no finding is P1. Seven confirmed P2 findings remain: four are in the gates and test harness, one is in immutability, one in log hygiene, and one in hosted key management.**

- **Gates and test harness (4):** some gates report green without checking what they are meant to check.
  - A narrowed `make ci` still prints `OK ci`.
  - `make test-pg` passes with skipped pg tests.
  - The engine-test database guard is missing.
  - `proc.sh` checks readiness on the wrong port.
- **Immutability (1):** partitions of append-only tables can be truncated without a data-fix ticket.
- **Log hygiene (1):** SQL bound parameters reach the error log.
- **Hosted key management (1):** the KEK is decrypted into process memory instead of wrapping DEKs through KMS.

Three of the seven are latent today: the partition, KMS and pg-skip defects. They become reachable in PLF, in hosted deployment, and with the first skipped pg test. There are 15 P3 findings, and 7 findings or finding parts are dropped.

Place SUP-FND-1 to SUP-FND-3 directly after GATE-FND in `docs/BUILD_SPEC.md` and copy them into `docs/build-spec/11-foundation-platform.md` (BSF-D-01). The loop then takes them before EKC-6, because they become the first unticked items. SUP-FND-2 must land before the PLF item that creates `audit_event`.

## Baseline (setup reviewer, `setup/baseline.md`)

**Every gate in the GATE-FND row is green in the review environment, and the counts equal the loop's recorded evidence.**

| Gate | Result |
|---|---|
| `make setup` twice | exit 0 both runs. `.env` and both lockfile hashes unchanged; alembic head `0003`; DB-14 lint 0 findings |
| `make ci` | exit 0, 32 s. Backend 242 passed, 0 failed, 0 skipped; Vitest 197 passed; mypy clean over 52 files; `worktree_dirty` false |
| `make ci` lint sub-steps | design-check 0 errors; vocab-check 0 findings; licence-check 45 packages, 0 findings; secrets-check 1,516 files, 0 findings; fixtures 18 verified; 0 tagged control tests; single alembic head |
| `make test-pg` | 24 passed, 0 failed, 0 skipped |
| `make fixtures CHECK=1` | 18 files verified |
| `erev controls-report --tags-only` | exit 0 |
| Readiness | `proc.sh start api 8192 …` answered readyz 200 only with `EREV_API_PORT` exported (FR-B-01). `make backend` was not run, because it binds the loop's port 8190 (FR-C-03) |

After all runs, `git status --porcelain` was empty and every process started by a reviewer was stopped by PID.

## Confirmed findings

Findings from the setup reviewer carry ids FR-B-01 to FR-B-05, which map to setup F-1 to F-5.

### P2

#### FR-G-01: `make ci` reports `OK ci` and `exit_code` 0 for a partial suite

- **Where:**
  - `Makefile:44-46`: `PYTEST_PATHS` and `RUN_VITEST` are derived from `TESTS` and `FRONTEND`.
  - `Makefile:206`: the test stage overrides only `SLOW`, so `TESTS`, `K` and `FRONTEND` reach the sub-make through `MAKEFLAGS`.
- **Contract:**
  - dev-guide §4.3 DG-MK-ci (`dev-guide:516`): stage 4 is `make test SLOW=1` with Vitest counts, and the target takes no variables.
  - BUILD_SPEC GK-01 (`:100`).
  - DG-MK-release-manifest (`:529`) decides PASS from `build_sha`, `exit_code` and `worktree_dirty` only.
- **Reproduction:**
  - `make ci TESTS=backend/tests/engine/test_canonical.py` printed `ci counts: backend 16 passed, 0 failed, 0 skipped` and `OK ci`, exit 0. `report.json` has `exit_code` 0, `failures []` and no `vitest` key.
  - `make ci K=test_canonical FRONTEND=0` printed `16 selected`, ran no Vitest, and ended `OK ci`.
  - Logs: `verify-gates-repro/logs/FR-G-01a-ci-TESTS.log`, `FR-G-01b-ci-K-FRONTEND.log`, `gates/logs/scratch/P12-ci-report.json`, `verify-gates-authority/probe-g01/probe-g01.log`.
- **Verdicts:** confirmed by both verifiers. The defect is latent: the latest real ci report in the main repo is un-narrowed.
- **Fix:** SUP-FND-1. `ci` refuses the three variables and records the refusal in `report.json`.

#### FR-G-02: G6 passes with skipped or xfailed pg tests; DG-TST-07 and DG-TST-09 are enforced only for control tests

- **Where:**
  - `backend/erev_api/controls/registry.py:34,129-130`: the skip rule fires only when a control marker is present.
  - `backend/tests/conftest.py:97-103` is the only collection hook.
  - `scripts/gate_report.py:107-121` treats pytest exit 0 as a pass and has no rule for skipped tests.
  - `Makefile:212-216`.
- **Contract:**
  - dev-guide §9.2 DG-TST-07 (`:1937`) and DG-TST-09 (`:1939`).
  - BUILD_SPEC XR-07 (`:146-147`).
  - GK-02 (`:101`): "Every pg test passes"; G6.
- **Reproduction:**
  - Setup: `pg/test_probe_skip.py` (module `pytestmark` pg; `@skip`, `@skipif`, `@xfail` on a failing test, and a runtime `pytest.skip`) plus `pg/test_probe_no_pytestmark.py` (a failing test, no marker).
  - `make test-pg K=probe` printed `3 skipped, 243 deselected, 1 xfailed`, `test-pg counts: backend 0 passed, 0 failed, 4 skipped` and `OK test-pg`, exit 0.
  - Control case: adding `control("CTL-001")` makes collection fail with exit 4.
  - Logs: `verify-gates-repro/logs/FR-G-02a-test-pg-probe.log`, `FR-G-02c-test-pg-control-contrast.log`, `verify-gates-authority/probe-g02/probe-g02.log`.
- **Verdicts:** confirmed by both verifiers. Latent: `backend/tests` has no skip or xfail today.
- **Fix:** SUP-FND-1. See also the SPEC-Q-45 ruling below.

#### FR-C-01: the DG-TST-18 engine isolation guard does not exist

- **Where:** `backend/tests/engine/conftest.py` is absent at `374edb3` and at main `9984d0d`, which already holds 12 engine test modules under `backend/tests/engine/kernel/`. `backend/tests/conftest.py:97-103` never inspects `fixturenames`.
- **Contract:** dev-guide §9.3 DG-TST-18 (`:1953`); BUILD_SPEC XR-07 (`:145`).
- **Reproduction:**
  - `git -C ~/dev/erev ls-tree -r --name-only HEAD backend/tests | grep conftest` prints only `backend/tests/conftest.py`.
  - Using the real conftest plus an engine test that requests `db`, `committed_db` and `test_database`, `pytest --setup-plan` plans `SETUP S test_database`, `SETUP F db` and `SETUP F committed_db`, and exits 0 (`verify-conformance-repro/verdicts.md`).
- **Verdicts:** confirmed by both verifiers; one called P3 arguable. The lead keeps P2: the guard is a named artifact, and EKC is adding engine tests now.
- **Fix:** SUP-FND-1.

#### FR-B-01 (setup F-1): `proc.sh start` polls readiness on the port from the environment, not the port it started

- **Where:**
  - `scripts/proc.sh:24-43`: `readiness` and `port_of` use `${EREV_API_PORT:-8190}` and the other port variables.
  - `:81-88`: `<port>` is used only for the holder check.
  - `:93`: `check_ready` never receives the port.
- **Contract:**
  - dev-guide §3.2 DG-RUN-10 step (4) (`:441`): poll the readiness check "of the process just started".
  - §3.1 intro (`:420`).
  - BUILD_SPEC GATE-FND Gates.
- **Reproduction:**
  - Baseline row 7': a healthy API on 8192 (a direct `GET /api/v1/readyz` returns 200) was reported `api not ready within 60 s`, exit 1. `status` showed `port=8190 ready=not-ready`.
  - The converse, by code reading: when anything answers 200 on 127.0.0.1:8190 (the loop's API), a start on another port reports ready without probing the started process.
- **Verdicts:** setup reviewer only. The lead confirmed it by reading `proc.sh:26,37,93`.
- **Fix:** SUP-FND-1.

#### FR-M-01: child partitions of IM-A tables can be truncated without `app.data_fix_ticket`, and DB-14 (g) never checks partitions

- **Where:**
  - `backend/erev_api/db/migration_ops.py:714-721`: the statement-level `BEFORE TRUNCATE` trigger is created on the parent only.
  - `:821-827`: `create_monthly_partitions` adds no trigger. PostgreSQL clones row triggers to partitions, but not statement triggers.
  - `backend/erev_api/db/lint.py:89-99` (`AND NOT c.relispartition`) and `:179`: check (g) looks at parents only.
- **Contract:**
  - 04 §14.1 DB-01 (`04:4802`): append-only tables "cannot be … truncated", using `BEFORE TRUNCATE … FOR EACH STATEMENT`.
  - 04 DB-14 (g).
  - dev-guide §6.5 DG-MIG-10.
  - The FND-6 `test_db_01_forbid_mutation` uses only an unpartitioned probe.
- **Reproduction:** run on `erev_rv_2` as `erev_owner` in rolled-back transactions.
  - `TRUNCATE` of the parent is refused with `EREV-IMM-001`, and `UPDATE` through a child is refused.
  - `TRUNCATE` of the `p202609` and `pdefault` children without a ticket succeeded ("rows left 0").
  - The children carry only `__immutable`, and DB-14 reports no (g) finding.
  - The result is the same when partitions are created before `apply_class`.
  - Evidence: `maintainability/probes/partition_truncate_probe.out`, `verify-maintainability-repro/probes/fr_m_01_partition_truncate.out`, `verify-maintainability-authority/probes/partition_truncate_order_probe.out`.
- **Impact:**
  - All three partitioned tables are IM-A: T-PLT-19 `audit_event`, T-ENG-02 `schedule_line` and T-SL-04 `subledger_line`. The PLF `audit_event` acceptance checks only child privileges, so the gap would pass the PLF gate.
  - Only `erev_owner` can reach it, because `erev_app` has no child privileges (04 §1.6 rule 3).
  - Latent: heads are at `0003`, and no partitioned table exists yet.
- **Verdicts:** confirmed by both verifiers.
- **Fix:** SUP-FND-2, before the PLF `audit_event` revision.

#### FR-S-02: bound SQL parameters and PostgreSQL value echoes reach the `http.unhandled_error` log line

- **Where:**
  - `backend/erev_api/db/session.py:152-160`: `create_engine` is called without `hide_parameters`.
  - `backend/erev_api/problems.py:266-271,278-283`: an unmapped `DBAPIError` is logged with `exc_info`.
  - `backend/erev_api/logging.py:98-108`: `_scrub_trace` redacts only secret assignments and e-mail addresses.
- **Contract:** dev-guide §6.6 DG-LOG-03 (`:1704`, which forbids amounts, personal data and contract text); 05 OPR-20, OPR-21, SAR-19; REQ-OPS-005.
- **Reproduction:**
  - Through `create_app` and `TestClient`, an unmapped `DBAPIError` (division by zero) raised inside `identity_session` returns a clean 500 about:blank. The log line, however, ends with `[parameters: {'amount': '146000.00', …}]`, including a synthetic display name and contract text.
  - An invalid numeric cast leaks `USD 98765.43` through the PostgreSQL message.
  - With `hide_parameters=True` the parameters are hidden.
  - Evidence: `security/probes/p02.out`, `verify-security-repro/probes/v02.out`, `verify-security-authority/v_nodb.out`.
- **Verdicts:** confirmed by both verifiers.
- **Fix:** SUP-FND-3.

#### FR-S-04: hosted `GcpKeyProvider` decrypts the KEK into process memory instead of wrapping DEKs through KMS

- **Where:**
  - `backend/erev_api/adapters/keys/provider.py:184-198`: `_load("kek:<n>")` reads version n of the Secret Manager secret `app-kek`, KMS-decrypts it and caches the plaintext.
  - `:127-142`: `wrap` and `unwrap` run AES-GCM locally.
  - `provider.py:36,140` and `auth/keyring.py:74`: the fixed `WRAPPED_DEK_BYTES` that SPEC-Q-15 relied on.
- **Contract:**
  - 05 §6.5 KEY-04 (`05:1089`), hosted: "Cloud KMS key `erev-app-kek` used through `encrypt`/`decrypt` calls on DEKs only", with automatic 90-day rotation.
  - 05 DPL-34 provisions the KMS key; DPL-36 provisions no `app-kek` secret.
  - 05 SAR-22's DEK cache assumes a remote unwrap.
  - dev-guide DG-KRN-KEY-04 specifies only `LocalKeyProvider.wrap`.
- **Reproduction:**
  - With fake KMS and Secret Manager clients, three `KeyRing.encrypt` calls make one KMS call in total: a decrypt of `erev-app-kek/versions/1`. There is no KMS encrypt.
  - The plaintext KEK is cached in `provider._keys` and returned by `hmac_key("kek:1")`.
  - Evidence: `verify-security-repro/probes/v04.out`.
- **Impact:**
  - The KEK can be extracted by any identity holding both `secretAccessor` and `cryptoKeyEncrypterDecrypter`.
  - It sits in the memory of every api and worker process.
  - KMS rotation does not rotate the effective KEK.
  - The provider depends on a secret that Terraform never creates.
- **Verdicts:** confirmed by both verifiers. Latent: this is a hosted artifact that is never instantiated (DG-ENV-17).
- **Fix:** SUP-FND-3. See also the SPEC-Q-15 ruling below.

### P3

| Id | Defect | Where | Contract | Evidence | Fix |
|---|---|---|---|---|---|
| FR-G-04 | `gate_report.py` silently drops a JUnit summary that was never written and still prints `OK` | `scripts/gate_report.py:118-121`; `test_makefile_targets.py:137-167` only checks labels | DG-MK-ci (`:516`); BUILD_SPEC FND-18 `test_dg_mk_00g_ci_report_fields` (`:845`); DG-GATE-04 | `gate_report.py ci --stage env=true --junit backend=<absent> --junit vitest=<absent>` printed `OK ci`; `report.json` `exit_code` 0 and counts `{stages}` only (`verify-gates-repro/logs/FR-G-04-missing-junit.log`). Reachable today only through FR-G-01 narrowing or path drift | SUP-FND-1 |
| FR-C-03 (setup F-2) | `make backend` and `make frontend` hardcode 8190 and ignore `EREV_API_PORT` | `Makefile:40-41,62-64,72`. `proc.sh:26,37` and `vite.config.ts:66` honour the variables | dev-guide §3.1 (`:420`); `.env.example` D-70 note (`:357`); DG-RUN-21. DG-MK-backend and DG-MK-frontend spell 8190, read here as the default | `env -u MAKEFLAGS EREV_API_PORT=8192 EREV_WEB_PORT=5272 make -n --no-print-directory backend frontend` prints `lsof -nP -iTCP:8190`, `--port 8190` and `EREV_API_PROXY_TARGET=http://127.0.0.1:8190`, so Vite binds 5272 but proxies to 8190. `make backend` refuses a busy 8190, so the loop's API is not taken over | SUP-FND-1 |
| FR-B-03 (setup F-3) | `make build` imports a module set different from DG-MK-build, with no spec question | `Makefile:39` `BUILD_IMPORTS := erev_api.cli, erev_api.main, erev_engine` | dev-guide §4.3 DG-MK-build (`:515`): `import erev_api.main, erev_api.worker, erev_engine`. `worker.py` arrives in PLF | Code reading; `grep worker docs/reviews/loop/spec-questions-FND.md` finds nothing | SUP-FND-1 (guard test) |
| FR-B-04 (setup F-4) | Tests write fixed scratch names into the shared `.run/` | `backend/tests/unit/test_registry_seed.py:21-24,33,43`; `test_proc_sh.py:12,30-32` (name `probe`) | dev-guide §3.4 DG-RUN-30; DG-DONE-09 | Setup baseline F-4: `.run/tmp/policies.py` (115,095 B), `POLICIES-pol-004-default-changed.md` and `.run/probe.log` remain after the session | SUP-FND-1 |
| FR-S-01 + FR-M-06 | The DG-ENV-13 allow-list checks only the URL path, so a query `dbname` redirects the connection. The allow-list is copied three times and parsed two ways | `db/session.py:103-111,166-172`; `config.py:39,257-266`; `db/session.py:31`; `scripts/check_env.py:43,76-85` | dev-guide §2.4 DG-ENV-13 (`:410`) and DG-ENV-11 (`:408`); `docs/00-GOAL.md` §5 | Path `erev_rv_1` plus `?dbname=erev_rv_3`: all three guards pass, the log says `database: erev_rv_1`, and `SELECT current_database()` returns `erev_rv_3` (`security/probes/p01.out`; `verify-security-repro/probes/v01.out`). For `…/erev_rv_x%5Fy`, `config` accepts `erev_rv_x_y` while `session` refuses. Destructive resets still re-check `current_database()` (`tests/support/db.py:57-59`; `cli.py:146-148`) | SUP-FND-2 |
| FR-C-04 | `identity_session` is used outside `erev_api.auth` (readyz and the catalogue lint) without a spec question | `api/v1/health.py:20,37-46`; `db/lint.py:229-234`; `erev_api/auth` has no repository yet | dev-guide §5.2 DG-KRN-DB-02 (`:647`) | `grep -rln identity_session backend/erev_api` lists `db/session.py`, `db/lint.py` and `api/v1/health.py`. §5.2 offers no compliant factory, and a new one would breach DG-KRN-DB-04 | SUP-FND-2 (ruling plus allow-list rule) |
| FR-M-03 | The ITGC guide claims a broader build control than DG-ARC-05 enforces | `docs/guides/itgc-guide.md:15`; `backend/tests/architecture/test_forbidden_patterns.py:86-91` | DG-ENV-14 first sentence (`:411`) vs its five-string list; FND-18 guide accuracy (REQ-CTL-004) | `check_source` returns `[]` for `DROP DATABASE`, `CREATE USER … SUPERUSER`, `ALTER USER erev_app BYPASSRLS`, `DROP ROLE`, `ALTER DATABASE … SET`, `CREATE TABLESPACE`, and `DROP` or `ALTER EXTENSION` (`verify-maintainability-authority/probes/dg_arc_05_synonyms.out`). The widened pattern has 0 hits in the repository (lead grep) | SUP-FND-2 (widen the rule so the guide is true) |
| FR-C-02 + FR-G-03 (narrowed) | The engine purity scanner misses aliased clock reads | `backend/tests/architecture/test_engine_purity.py:77-80,90-91`; `backend/tests/support/architecture.py:96-104` drops `asname` | BUILD_SPEC XR-20 (`:174`); DG-ARC-02 (`:1763`) as extended by SPEC-Q-49 (".now, .today, .utcnow on them are findings") | `check_purity('backend/erev_engine/stages/x.py', 'from datetime import datetime as dt\nknown_at = dt.now()\n')` gives 0 findings (the unaliased form gives 1), and `D.today()` gives 0 (`verify-gates-repro/logs/FR-G-03-alias-probes.log`). No aliased import exists today | SUP-FND-2 |
| FR-M-04 (narrowed) | The runbook misstates how a failed migration is rolled back | `docs/guides/runbook.md:99`: "rolled back by restoring that backup (05 OPR-11)" | 05 OPR-16 (`05:1259`): rollback is restore by OPR-11. 05 OPR-11 (`05:1256`): restore is PITR clone and cutover; "Production data is never restored in place" | Text comparison | SUP-FND-2 |
| FR-S-03 | `KeyProvider.secret(ref)` returns the master keys to any caller that names them. Latent until DIN-12 | `adapters/keys/provider.py:156-157,200-201`; `adapters/secrets/store.py:32-43` | 05 KEY-09 (local adapter credentials: none); 05 ADP-14; 04 T-INT-01 `secret_ref` (`04:4493`) is a free name; dev-guide DG-KRN-KEY-01 | `provider.secret('EREV_ENCRYPTION_KEY')` equals the master key, and HKDF over the returned value reproduces `kek:1` (`security/probes/p03.out`; `verify-security-repro/probes/v03.out`) | SUP-FND-3, plus a DIN-12 ruling (below) |
| FR-S-05 | `MoneyStr`, `DecimalStr` and `RateStr` accept non-ASCII Unicode digits | `backend/erev_api/money.py:28-30` (`\d` without `re.ASCII`) | 04 API-C-06 (`04:3243`, `[0-9]`); dev-guide DG-KRN-MONEY-05, -06 | Arabic-Indic and fullwidth `12.30` return 200 with minor 1230; `DecimalStr "٠.٢٥"` and `RateStr "١.٠٨"` are accepted (`security/probes/p04.out`; `verify-security-repro/probes/v05.out`). The conversion is exact, so no accounting error | SUP-FND-3 |
| FR-S-06 | Log hygiene keeps secret keys nested inside mappings, and redacts only the first word of a passphrase | `backend/erev_api/logging.py:67-70,111-119`; `backend/tests/support/log_guard.py:36-54` | 05 SAR-19 (`05:1111`); DG-LOG-03; DG-LOG-07 | `error_codes={'password': 'nested-secret-value'}` survives, and `password=[REDACTED] horse battery staple` is logged; `log_guard.check` passes a nested password (`security/probes/p05.out`; `verify-security-repro/probes/v06.out`). The dotless e-mail point is dropped, because DG-LOG-07 defines no pattern | SUP-FND-3 |
| FR-S-07 | uvicorn records bypass the structlog JSON and hygiene pipeline | `backend/erev_api/logging.py:183-187` (root handler only); uvicorn `LOGGING_CONFIG` sets `propagate: False` | dev-guide §3.4 DG-RUN-31 (`:463`); DG-LOG-01; DG-LOG-06 | `grep -vc '^{' .run/api.log` returns 16 of 24 lines. A route failing after the response started printed an unredacted `Exception in ASGI application` traceback holding a synthetic secret (`verify-security-repro/probes/v07.out`) | SUP-FND-3 |
| FR-S-09 | No item builds the 05 SAR-12 CORS middleware, and `EREV_CORS_ORIGINS='*'` is accepted | `backend/erev_api/config.py:175-180`; `backend/erev_api/main.py:34-48`; BUILD_SPEC mentions CORS only at `:388` and `:9889` | 05 SAR-12 (`05:1140`) | It fails closed: `OPTIONS` returns 405 with no ACAO header (`security/probes/p10.out`; `verify-security-repro/probes/v09.out`). This is a spec coverage gap, not an FND acceptance failure | SUP-FND-3 (rejection in `create_app`, so SOP `test_sar_40_production_checks` can still report `*`) |
| FR-B-05 (setup F-5) | `make lint` emits `PytestAssertRewriteWarning … anyio` | In-process pytest of `erev controls-report --tags-only` | DG-DONE hygiene | `setup/controls-tags-only.log:4`; `setup/ci.log:24` | Not remediated: no effect on any gate, and the fix needs investigation |

## Dropped findings

| Id | Reason |
|---|---|
| FR-M-02 | **Both verifiers refuted it.** The contracts prescribe seeding from the live constants: DG-MIG-07 (`dev-guide:1692`), DG-KRN-PERM-01 and FND-7 scope. Supervisor design note: drift of long-lived databases, and `add_enum_value` without `IF NOT EXISTS` (`migration_ops.py:315-317`) |
| FR-S-08 | **Lead adjudication: refuted.** DG-MK-secrets-check step (2) skips "binary files" without defining the term. `secrets_check.py:143-148` uses git's NUL-byte test, and git itself treats the probe files as binary. All 24 skipped worktree files are real binaries (`verify-security-repro/probes/v08_repo_skipped.txt`). Optional hardening only |
| FR-M-05 | **Lead adjudication: refuted.** The DG-FE-17 flags are set, and DG-FE-12 concerns CSP. No non-test file under `frontend/src` uses Node globals, and the DS-VER suites legitimately need Node types (SPEC-Q-55, SPEC-Q-57) |
| FR-M-07 | **Lead adjudication: refuted.** Committed revisions 0001 to 0003 comply with DG-MIG-02. FND-6 `test_dg_mig_02_revision_renderer` passes. DG-MK-revision cannot know the table ids, and the "no-op passes the round trip" claim was inferred, not run |
| FR-M-08 | **Lead adjudication: refuted.** No contract requires an OpenAPI export that runs without secrets. `create_app()` is the documented composition root (SPEC-Q-41), and stage 1 of `make ci` validates the environment first |
| FR-C-02 / FR-G-03, DG-ARC-05 and DG-ARC-06 parts | DG-ARC-05 (`:1766`), DG-KRN-TIME-05 (`:1040`) and DG-ARC-06 / DG-KRN-MONEY-04 (`:993`) name literal tokens, and the regexes match them. Only the engine purity part is kept |
| FR-M-04 part (a) | `proc.sh:93-99` and `runbook.md:31-36` match dev-guide DG-RUN-10 steps (1) and (4), which prescribe exit 1 without stopping the child |

## Spec-question rulings (loop calls shown wrong)

| SPEC-Q | Loop call | Ruling |
|---|---|---|
| SPEC-Q-15 | Hosted `GcpKeyProvider` KMS-decrypts `app-kek` once per process and wraps DEKs locally, to keep one fixed blob layout | **Wrong.** The fixed wrapped-DEK length comes from the loop's own `WRAPPED_DEK_BYTES`, not from DG-KRN-KEY-04, and the call contradicts 05 KEY-04, DPL-34, DPL-36 and the KMS rotation column. Ruling: `GcpKeyProvider.wrap` and `unwrap` are Cloud KMS `encrypt` and `decrypt` on the DEK, with the canonical context bytes as additional authenticated data. The blob carries a 2-byte wrapped-DEK length for both providers, and `GcpKeyProvider` never loads KEK material. Applied by SUP-FND-3 |
| SPEC-Q-45 (with SPEC-Q-11) | SPEC-Q-11 deferred DG-TST-06 and DG-TST-07 enforcement to `controls.yaml`; SPEC-Q-45 enforced DG-TST-09 for control tests only | **Scope wrong.** DG-TST-09 names parity, answer_key, property, pg and control tests, and DG-TST-07 was never enforced. Ruling: the collection hook enforces DG-TST-07 and DG-TST-09 for all five markers, keeping the DG-TST-02 architecture exception, and `make test-pg` fails on any skipped test. Applied by SUP-FND-1 |

**Supervisor rulings carried by the items (D-70; none had a spec question):**

- `identity_session` may be used by `erev_api/auth`, readyz (05 OPR-23) and `lint_as_app` (DG-MK-migrate step 3). No fourth factory, per DG-KRN-DB-04. Applied by SUP-FND-2.
- DG-ARC-05 enforces the whole first sentence of DG-ENV-14. Applied by SUP-FND-2.
- `make build` imports `erev_api.worker` once `backend/erev_api/worker.py` exists. Applied by SUP-FND-1.
- `make ci` refuses `TESTS`, `K` and `FRONTEND`. Applied by SUP-FND-1.
- The `proc.sh` readiness URL comes from the start `<port>`. Applied by SUP-FND-1.
- The hosted adapters may be unit-tested with fake clients, with no `google.cloud` import and no network. This amends DG-ENV-17 "never exercised in tests". Applied by SUP-FND-3.
- DIN-12 resolves `secret_ref` through `KeyProvider.secret` (05 ADP-14), not directly through `SecretStore`, so the key-material refusal applies. This amends `BUILD_SPEC:6414`.

## Observations below the finding bar

- **Loop claim inaccuracy:** SPEC-Q-25 says 159 currency codes, but `ISO_4217` holds 164.
- **04 disagrees with itself on IM-P DELETE:** §1.5 has no DELETE for IM-P, while §14.2 grants DELETE on DRAFT rows. The code follows §14.2.
- **dev-guide pattern gap:** the dev-guide `PASSWORD_ASSIGNMENT` pattern misses `DB_PASSWORD = "…"` and `password: str = "…"`. The implementation copies the spec.
- **DG-ARC-05 token list:** `datetime.today()` is not in the list.
- **Unverified storage defect:** `LocalFileStore.put` on an existing non-SHA-256 key keeps the old object but returns the new stream's hash (`security/probes/p09.out`). Check it before PLF uploads.
- **Security-lens notes:**
  - The licence resolver takes the first source that parses.
  - The key-id cache is unbounded.
  - `ensure_keys` sets mode 0600 only when it creates `.env`.
- **Maintainability-lens notes:**
  - The ESLint override for `src/lib/format` disables every `no-restricted-syntax` selector.
  - readyz re-parses the versions directory on every call.
