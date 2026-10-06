# P4: SAR-40 production doctor predicates (SOP-6, first phase)

Lane record for platform lane P4 on `sprint/l15` (worktree `~/dev/erev-wt/l15`, base main `045a212`).
Dispatch: supervisor, 2026-09-19 13:35 PDT, from `PRODUCTION-LOCAL-DISPATCH-AUDIT-bb6b845.md` item 3 and
`docs/reviews/loop/prod/lanes/P4.md` scope item 2. Source-only phase: no database was created or read, no
server, no Docker, no cloud call, no DB gate stage (admission hold in force for the whole lane). Binding
text: 05 SAR-40 (rev 1.10 below; authored as 1.9 and renumbered after main's lane D1 merge took 1.9), SAR-09, SAR-12, UPL-05, REL-03, CFG-01, CFG-09 to CFG-11, CFG-13, CFG-17,
CFG-30, KEY-03, KEY-10; 04 §1.6 rules 1 and 2, T-INT-01; dev-guide DG-MK-doctor, DG-KRN-AUTH-07, DG-ARC-01,
DG-ARC-03; BUILD_SPEC SOP-6 (`docs/BUILD_SPEC.md:10912-10937`); runbook RB-03.

## Commits (`sprint/l15`, main..HEAD)

| Commit | Files | Change | Gate evidence |
|---|---|---|---|
| `111d00c` | `docs/05-ARCHITECTURE.md` (header, revision log 1.9 → renumbered 1.10 in the follow-up commit, §6.18 SAR-40), `docs/dev-guide.md` (header, revision log 1.13 → 1.14, §4.2 DG-MK-doctor), `docs/guides/runbook.md` (RB-03 "Production checks (05 SAR-40)") | Docs first: the six SAR-40 conditions become named checks with stated observation rules; `WARN anthropic-key`; four production checks added (`release-stamp`, `key-provider`, `key-version-pin`, `recovery-provider`); fail-closed and pending-lane WARN rules; no production check runs outside `production` | `make lint` exit 0 (46 s); `tests/unit/test_guides.py` 3 passed |
| `ca232ba` | `backend/erev_api/controls/doctor.py` (+~590 lines), `backend/tests/unit/test_doctor_production_checks.py` (new, 40 tests) | Predicates, observations, injected collector, `run_doctor(production=...)` hook, `CheckResult.warnings` | `make lint` exit 0 (30 s); `make typecheck` exit 0 (mypy strict, 561 files; tsc); `backend/tests/architecture` 72 passed; `test_config.py`, `test_guides.py`, `test_makefile_targets.py`, `test_controls_report.py` 38 passed; new module 40 passed |
| `315a337` | `docs/reviews/loop/prod/P4-doctor.md` | Record | `make lint` exit 0 (33 s) |
| `88b2e58` | `docs/05-ARCHITECTURE.md`, `docs/dev-guide.md`, this record | Revision renumbering 1.9 → 1.10 and 1.13 → 1.14 after main's lane D1 merge took those numbers; the four added checks worded as a supervisor amendment sourced from the dispatch audit; questions (1), (2) and (6) recorded as resolved. Merged to main as `9f37c39` (supervisor; both revision entries kept) | `make lint` exit 0 |
| `88b84aa` | `docs/guides/runbook.md` | Codex follow-up, docs first: RB-03 rows for the pin (collected, well-formed current key id; ASCII-digit pin), the undefined-setting WARN (a supplied value is not read), and release-stamp absence | `make lint` exit 0; `test_guides.py` 3 passed |
| `35baeb7` | `backend/erev_api/controls/doctor.py`, `backend/tests/unit/test_doctor_production_checks.py` (57 tests) | Codex P4-R1 to P4-R4 corrections (section below) | `make lint` exit 0; `make typecheck` exit 0; architecture + related unit files 110 passed; module 57 passed |
| `6f35410` | this record | Codex follow-up section | `make lint` exit 0 |
| `6f475aa` | `docs/dev-guide.md` (header, revision log 1.15, §4.2 DG-MK-doctor), this record | Supervisor ruling (4): DG-MK-doctor states the `OK` / `FAIL` / `WARN` line kinds and their exit semantics | `make lint` exit 0 |
| `426b818`, `e44227b`, this commit | P4b (section below) | Real collectors with provenance, CLI composition, SOP-1/7 inventory | `make lint` exit 0 each; see the P4b gate table |

Commit messages end with the required co-author line. No push, rebase, reset, stash, amend, clean or
checkout of another branch; scratch under `.run/p4/`; nothing killed.

## Spec applied

SAR-40 as amended in rev 1.10 (a supervisor amendment under the production objective, applied through
this dispatch and sourced from the dispatch audit, not a ruling of Ray's; authored as 1.9 and renumbered,
with dev-guide 1.13 → 1.14, after main's lane D1 merge took those numbers). Each condition is one check in the RB-03 line format, with the observation rule the
predicate implements:

| Check | SAR-40 condition | Observation and rule as implemented |
|---|---|---|
| `email-backend` | `EREV_EMAIL_BACKEND = fake` | snapshot `email_backend == "fake"` fails (CFG-17) |
| `integration-urls` | an active integration connection has a loopback or private base URL | per `ACTIVE` `IntegrationConnectionObservation` with a `base_url`: `private_url_reason` flags a literal loopback, link-local, unspecified or private address (`ipaddress`), the name `localhost`, a `.localhost`, `.local` or `.internal` name, a single-label host, or a URL without a host; `DISABLED` rows and a null `base_url` (KEY-09: default provider endpoint) pass |
| `cors-origins` | `EREV_CORS_ORIGINS` contains `*` | any origin containing `*` fails (SAR-12); empty means CORS disabled |
| `session-cookie` | the session cookie would not be `Secure` | observed through `EREV_PUBLIC_ORIGIN`: a `127.0.0.1`, `localhost` or `::1` host fails (DG-KRN-AUTH-07 omits `Secure` for the loopback request host); a scheme other than `https` fails (a browser never returns a `Secure` cookie to it, SAR-09). Judgement call, see Questions (1) |
| `defusedxml` | `openpyxl.DEFUSEDXML` is false | injected bool from `observe_defusedxml` (UPL-05) |
| `partition-window` | the partition window ends within 12 months | for every table in `migration_ops.PARTITION_COLUMNS` (`audit_event`, `schedule_line`, `subledger_line`) plus any observed extra: no observation fails; `ends_on is None` (no bounded partition, §1.6 rule 1) fails; `ends_on <= today + 12 calendar months` fails (boundary: a window ending exactly on the horizon fails, one day later passes) |
| `anthropic-key` | warning (exit 0) when `EREV_AI_PROVIDER = anthropic` and no `ANTHROPIC_API_KEY` secret resolves | `WARN` line, `ok` stays true; the probe result falls back to `Settings.anthropic_api_key is not None` (KEY-10) |
| `release-stamp` (rev 1.10) | REL-03 | `observe_release` wraps `release_facts`: a `ReleaseManifestError` (absent in production, wrong engine version or schema head, malformed) is the finding |
| `key-provider` (rev 1.10) | CFG-11, CFG-13 | `local` passes (compose shape); `gcp` requires `EREV_GCP_PROJECT` and `EREV_GCP_KMS_KEK` set and a `ProviderObservation` with `healthy` true; an unhealthy probe fails under either provider |
| `key-version-pin` (rev 1.10) | KEY-03 | `EREV_SECURITY_HMAC_SECRET_VERSION` set and a positive integer; when the provider reports its current `security-hmac:<n>` key id, `n` must equal the pin; undefined by the build → `WARN … pending lane P2 merge` |
| `recovery-provider` (rev 1.10) | CFG-30, D-95 | value `NATIVE` or `MANAGED` (case-insensitive), consistent with `EREV_KEY_PROVIDER` (`local → NATIVE`, `gcp → MANAGED`; a contradiction is the only finding); unset defaults from the key provider; `NATIVE` requires `EREV_BACKUP_URL` and `EREV_RESTORE_ADMIN_URL` set, `MANAGED` refuses either set; undefined by the build and unset → `WARN … pending lane P6 merge`, then the default applies |

Two rules from rev 1.10 apply to all of them under `production`: an observation the collector did not
produce (`None`) fails closed with `FAIL <check>: <observation> was not collected; the SOP-6 collector is
pending`; outside `production`, `production_checks` returns `[]` and nothing prints.

## Design

- Observations (frozen dataclasses in `controls/doctor.py`): `SettingsSnapshot` (non-secret; recovery URLs
  as set/unset only; `undefined` lists documented names this build's `Settings` does not define),
  `IntegrationConnectionObservation` (T-INT-01 `tenant_code, code, status, base_url`),
  `PartitionWindowObservation` (`table`, exclusive upper bound `ends_on` of the last bounded partition),
  `ReleaseObservation`, `ProviderObservation` (`kind, identity, healthy, security_hmac_key_id, detail`),
  `ProductionObservations` (all of the above; `None` = not collected).
- Predicates: one function per check, pure, returning `CheckResult`; `production_checks(observations,
  now=)` applies them in `PRODUCTION_CHECK_NAMES` order under `production` only.
- `CheckResult` gains `warnings`; `lines()` prints `FAIL` per finding, else `WARN` per warning, else the
  `OK` line. `ok` is unchanged (warnings do not fail), so the five baseline checks and `tests/pg/test_doctor.py`
  are unaffected.
- Collector: `collect_production_observations(settings, environ=, defusedxml=, anthropic_key_resolves=,
  integration_connections=, partition_windows=, release=, provider=)` — every source injected;
  `observe_defusedxml` (imports `openpyxl` lazily) and `observe_release` (no database: `code_head()` reads
  the migration files) are real; the database collectors and the provider probe default to "not
  collected". `snapshot_settings(settings, environ)` reads the pending names from `environ` when the
  `Settings` field is absent, so a deployment can set them before the owning lane merges.
- `run_doctor(..., production: ProductionObservations | None = None)` appends the production results when
  observations are passed; `cli.py` is unchanged (later phase).
- Layering (DG-ARC-01): `controls` is a kernel module; the new code imports `config`, `controls.release`,
  `db.migration_ops` (kernel) and stdlib only; no adapter types cross into the doctor — the provider
  probe arrives as plain data from the composition root. DG-ARC-03: no `get_settings` call.
- Pending-merge names, verified against the owning branches: `sprint/l7` (P2) defines
  `Settings.security_hmac_secret_version` with alias `EREV_SECURITY_HMAC_SECRET_VERSION` (int, required
  under production); after that merge `snapshot_settings` reads the field and `undefined` shrinks
  without a code change (the unit test computes its expectation from `Settings.model_fields`).
  `sprint/l8` (P6) resolves `EREV_RECOVERY_PROVIDER` in `controls/recovery_preflight.py` from the
  environment and `.env`, not through `Settings`; the snapshot therefore keeps reading it from the
  injected `environ`, and the CLI phase should pass `os.environ` (composition root) or reuse P6's
  `resolve_recovery_provider` once merged. Neither branch's files were modified here.

## Fail-first evidence

Base for the "before" run: `111d00c` (the docs commit; code identical to main `045a212`).

```
$ backend/.venv/bin/pytest tests/unit/test_doctor_production_checks.py -q          # on 111d00c
tests/unit/test_doctor_production_checks.py:20: in <module>
    from erev_api.controls.doctor import (
E   ImportError: cannot import name 'ANTHROPIC_KEY' from 'erev_api.controls.doctor'
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.17s
exit=2
$ backend/.venv/bin/pytest tests/unit/test_doctor_production_checks.py -q          # on ca232ba
40 passed in 0.44s
exit=0
```

Logs: `.run/p4/fail-first-before.log`, `.run/p4/fail-first-after.log` (scratch, untracked). Inside the
module, `test_sar_40_production_checks` (the SOP-6-named test) seeds each of the six SAR-40 conditions
and asserts that exactly the named check fails with `FAIL <check>: …` lines, then that the good
observations pass all eleven checks with one `OK` line each, then that the Anthropic case yields one
`WARN anthropic-key: …` line with `ok` true. The 40 tests: 13 functions, of which
`test_uncollected_observation_fails_closed` ×5, `test_production_checks_do_not_run_outside_production` ×3
and `test_private_url_reason` ×22 are parametrised.

## Gates (measured on `ca232ba`; none projected)

| Gate | Result |
|---|---|
| `make lint` | exit 0 (`OK lint`; controls-report `--tags-only` 175 tagged tests valid) |
| `make typecheck` | exit 0 (mypy `--strict`: "no issues found in 561 source files"; tsc) |
| `backend/tests/architecture` | 72 passed (23.6 s) |
| `backend/tests/unit/test_doctor_production_checks.py` | 40 passed |
| `test_config.py`, `test_guides.py`, `test_makefile_targets.py`, `test_controls_report.py` | 38 passed |
| `make ci` | not run (frontend and full backend suite; DB-free but heavy under load 24 on 18 cores; left to the merge chain) |
| `make test-pg`, `make doctor` | not run: DB-stage admission hold; no database exists for this lane |

Environment: `.env` with `erev_rv_l15_dev/test/e2e`, ports 8186/5266 (e2e 8286/5366), regenerated
secrets; `uv sync --project backend --frozen`; `frontend/node_modules` was first a symlink to `l12`'s install
(identical `package-lock.json`; the `l13` precedent) and served the first two lint runs; then `l12`'s tree
changed underneath it (its top-level entry count moved 378 → 379 → 374 within twenty minutes) and
`licence-check`'s `npm ls --omit=dev --all` reported missing and extraneous packages, failing `make lint`
on the record run. The lane replaced the symlink with its own `npm --prefix frontend ci` from the lock
file before the record commit. Lesson for sibling lanes: a shared `node_modules` is not stable while its
owner runs npm.

## Open (later SOP-6 phases; explicitly not delivered here)

1. Database collectors: the active-connection list needs T-INT-01 `integration_connection`, which does
   not exist on main yet (only `subledger_line.integration_connection_id` references it; the table
   arrives with the INT lane) — collect per tenant through a read-only tenant session as `audit_chain`
   does; the partition window needs one catalogue query over `pg_inherits` / `pg_get_expr(relpartbound)`
   per `PARTITION_COLUMNS` parent, excluding the `DEFAULT` partition, returning the exclusive upper bound.
2. Provider probe: `ProviderObservation` from the composition root — `KeyRing` exposes no public
   accessor for the provider's `current_hmac_key_id("security-hmac", None)` or its identity; the CLI
   phase adds one (kernel `auth/keyring.py`, the DG-ARC-01 adapter factory) or probes through the
   existing `readyz` key-provider path.
3. CLI wiring: `cli.py doctor` builds `collect_production_observations(get_settings(), environ=os.environ,
   …)` (composition root) and passes `production=` to `run_doctor`; `--db dev|test|e2e` forces a local
   environment so the production checks never run under it; `tests/pg/test_doctor.py` line-count
   assertions stay valid because nothing prints outside `production`. The compose verification profile
   (`production` + `local` + a `127.0.0.1` origin, no recovery URLs) fails `session-cookie` and
   `recovery-provider` by design (DPL-16 does not run doctor; lane package gate note).
4. REL-07 unknown-setting-reference check and `tests/pg/test_doctor.py::test_rel_07_unknown_setting_reference`.
5. `--analyze <tables>` as `erev_owner` (DG-MK-perf-seed step 4).
6. `docs/guides/itgc-guide.md` section "Deployment self-check" (SOP-6 paths).
7. `make doctor` exit 0 on the dev database (SOP-6 evidence), `make ci`, `make test-pg`.
8. SOP-5 remains the SOP-6 prerequisite; this phase does not tick SOP-6.

## Questions for the supervisor (returned; (1), (2) and (6) resolved by the supervisor after 111d00c)

1. Confirmed: `session-cookie` fails a non-`https` `EREV_PUBLIC_ORIGIN` as well as a loopback host; a
   `Secure` cookie is never returned over http and production must be https.
2. Confirmed: the four rev 1.10 additions (`release-stamp`, `key-provider`, `key-version-pin`,
   `recovery-provider`) extend SAR-40 as a supervisor amendment under the production objective, sourced
   from the dispatch audit and not attributed to Ray; the 05 revision row says so.
3. `recovery-provider` under `production` + `EREV_KEY_PROVIDER=local` without the two URLs fails, per
   CFG-30 literally. Confirm the compose production profile stays undoctored (P4 package question), or
   whether an `EREV_DOCTOR_PROFILE=verification` exemption is wanted.
4. `WARN <check>: <finding>` as a third line kind in the RB-03 output contract (SAR-40 requires a
   printed warning; the exact form was unspecified).
5. Breadth of "loopback or private base URL": single-label host names and `.local` / `.internal` names
   are treated as private. Narrow to literal addresses plus `localhost` if preferred.
6. Resolved: main's lane D1 merge took 05 rev 1.9 and dev-guide rev 1.13 first; the lane renumbered its
   entries to 1.10 and 1.14 on the branch (the 05 header lists 1.10 above 1.8; the merge inserts main's 1.9).
7. The P4 package's own return questions remain open: the `security.ratelimit` path (P5), CTL-050's
   meaning, and the compose-profile exemption above.

## Residual limits

- Predicates are exercised only through unit tests with seeded observations; no run through `erev doctor`.
- `observe_release` with default arguments reads the repository-root `release-manifest.json` and may
  invoke `git rev-parse` outside `production` (as `release.py` already does); tests inject `build_sha`.
- `snapshot_settings` reads pending names from `environ` when given; the values of the recovery URLs are
  never held, only their presence.
- The lane branch is two commits plus this record ahead of main; no merge performed.

## Codex review follow-up (PRODUCTION-P4-DOCTOR-REVIEW-ca232ba; 51/60 controls)

Review file SHA-256 `fb1a7521894eb67226ba5a2aa3e12cf8cc7e834a0b8c0d6cd588085f8bd4a824`, reviewing code
`ca232ba` and docs `111d00c`; nine failed observations across four findings, all corrected on `sprint/l15`
after `git merge --ff-only main` (main `9f37c39`). Docs first in `88b84aa`, code and tests in `35baeb7`.

| Finding | Correction in `35baeb7` | Named regression cases |
|---|---|---|
| P4-R1 missing key identity became OK | `key_version_pin` fails with `the provider's current security-hmac key id was not collected; EREV_SECURITY_HMAC_SECRET_VERSION=<n> is not verified (05 KEY-03, SAR-40)` when the provider observation is missing or reports no key id, and fails a malformed key id (`security-hmac:<ASCII digits>` required); a configured pin never counts as a verified match without the collected identity. The producer expectation "unprobed pin → OK" (formerly `test_release_stamp_key_provider_and_version_pin`) is corrected; the compose shape passes only with a collected local key id | `test_r1_unknown_current_key_identity_is_a_named_fail` (silent healthy provider, missing provider, four malformed ids); `test_r1_run_doctor_composition_carries_the_pin_failure` (the real `run_doctor` body with its five database checks and sessions replaced by sentinels: 16 ordered results, pin FAIL; 16 OK with the full observation; five without observations); `test_uncollected_observation_fails_closed[provider]` now expects `key-provider` and `key-version-pin` |
| P4-R2 supplied values hid the unsupported-build WARN | `snapshot_settings` never reads a value for a variable the build defines neither through a `Settings` field nor through the owning lane's module (`_DEFINING_MODULES`: `EREV_RECOVERY_PROVIDER` → `erev_api.controls.recovery_preflight`, because lane P6 resolves CFG-30 from the environment, not `Settings`); `key_version_pin` and `recovery_provider` print the RB-03 `WARN <check>: <variable> is not defined by this build (pending lane <n> merge); not checked` before reading anything. Consequence: while undefined, `recovery-provider` no longer defaults from the key provider and checks the URLs; it is WARN-only until lane P6 merges (the earlier record sentence "then the default applies" is superseded) | `test_r2_supplied_values_never_hide_the_undefined_warning` (pin 3/2/three; recovery MANAGED/NATIVE/cloud → WARN only); `test_collect_production_observations_injects_every_collector` and `test_snapshot_settings_reads_documented_names_and_carries_no_secret` through the actual snapshot/collector composition (branching on whether the build defines the name, so they hold after the P2 and P6 merges) |
| P4-R3 explicit absent manifest accepted | `release_stamp` fails `manifest_present=False` regardless of `error`: `release-manifest.json is absent; production requires the release manifest (05 REL-03)`; the "derived" summary branch is removed | `test_r3_absent_manifest_observation_fails_closed` (build_sha None, "dev", a full sha) |
| P4-R4 malformed pin aborted the check list | The pin is parsed by `[0-9]{1,7}` with a positive value (never `str.isdigit` + `int`), failing with `INVALID_PIN` (`… must be a positive integer version number of at most 7 ASCII digits`); the provider key id is parsed the same way | `test_r4_malformed_pin_text_is_a_named_fail` (13 texts incl. `²`, `٣`, `３`, `1e3`, `-1`, `+3`, `0`, `""`, ` 3`, `3 `, `00000000`, `3.0`); asserts the eleven checks are returned in order |

Fail-first evidence: on `88b84aa` (code identical to main `9f37c39`) the edited module ran **22 failed, 35
passed, exit 1** (`.run/p4/r-fail-first-before.log`); on `35baeb7` **57 passed, exit 0**
(`.run/p4/r-fail-first-after.log`). Gates measured on `35baeb7`: `make lint` exit 0; `make typecheck` exit
0 (mypy strict, tsc); `backend/tests/architecture` + `test_config.py` + `test_guides.py` +
`test_makefile_targets.py` + `test_controls_report.py` 110 passed. No DB stage, no `.env` read, no process
beyond the test runs.

Unchanged by design (explicitly unfinished, not a regression): the real collectors (connections, partition
windows, provider probe), the CLI environment binding and `production=` wiring, REL-07, `--analyze`,
approved-registry-version enforcement, the ITGC guide section and the remaining SOP-6 acceptance tests
remain the later P4b phase; the current five-check `erev doctor` exit 0 establishes no SAR-40 coverage
(review §"run_doctor and completion boundaries"). Codex retests before acceptance.

## P4b: real collectors and CLI composition (SOP-6 second phase)

Dispatch: supervisor, 2026-09-19, "ready preparation" while the DB-stage hold stands; branch fast-forwarded to
main `eb5546a` before the commits. Scope delivered: (1) the production observation collectors with provenance,
(2) `erev doctor` under `EREV_ENV=production` running `production_checks` through the real composition path,
(3) the SOP-1 / SOP-7 execution and audit inventory, (4) docs first. CPU-only gates; no DB stage, no `.env`
read beyond `Settings`, no process beyond the test runs.

| Commit | Files | Change | Gate evidence |
|---|---|---|---|
| `426b818` | `docs/guides/runbook.md` (RB-03 "How the command collects", "What the command writes"), `docs/dev-guide.md` (header, revision log 1.16, §4.2 DG-MK-doctor) | Docs first: the composed collectors, the provenance form `FAIL <check>: <observation> was not collected: <reason>`, one `PLATFORM_SCOPE_USED` per run, the SOP-1/7 inventory | `make lint` exit 0; `test_guides.py` 3 passed |
| `e44227b` | `backend/erev_api/controls/doctor.py`, `backend/erev_api/cli.py`, `backend/tests/unit/test_doctor_production_checks.py` (70 tests) | Collectors, `Provenance`, `CollectorPending`, `production_collector`, `run_doctor` collector hook, CLI composition | `make lint` exit 0; `make typecheck` exit 0; architecture + related unit files 114 passed; module 70 passed |

Merged to main as `c8899be` (supervisor: lint 0, typecheck 0, architecture + doctor / config / guides / makefile /
controls-report / cli-health unit files 184 passed; the dev-guide revision row collided with main's 1.16 and was
renumbered to 1.17 at merge, both rows kept). Status: merged, not accepted until Codex retests `e44227b`.

### Design

- `Provenance(member, source, collected_at, error)` per `ProductionObservations` member; `collect_production_observations`
  takes the instant (`now`) and runs every collector through `_collect`, which turns any exception into a
  `None` member with the redacted reason (`redact`: URL credentials replaced, 300 characters) instead of an
  abort. `production_checks` rewrites the RB-03 `was not collected; the SOP-6 collector is pending` finding of an
  uncollected member into `was not collected: <reason>` from the provenance (`_MEMBER_OF_CHECK`).
- Real collectors (kernel module, plain data out): `observe_release` (manifest; `MANIFEST_PATH` looked up at
  call time so tests redirect it), `observe_key_provider` (identity from `Settings`, the current `security-hmac`
  key id through `KeyRing.current_security_key_id()`, a `security_event_key` derivation probe of that id;
  `CollectorPending` while the accessor is absent — lane P2), `observe_integration_connections` (T-INT-01 rows of
  every workspace through read-only tenant sessions over the tenant directory `run_doctor` already read;
  `CollectorPending` while `erev_api.db.tables.integration_connection` is absent — INT lane),
  `observe_partition_windows` (`pg_inherits` + `pg_get_expr(relpartbound)` per `PARTITION_COLUMNS` parent,
  `DEFAULT` excluded; `partition_upper_bound` parses the exclusive `TO` date), `observe_anthropic_key`
  (`ANTHROPIC_API_KEY`, or under `gcp` for the `anthropic` provider the Secret Manager reference
  `anthropic-api-key`, 05 KEY-10, through `KeyRing.secret`; nothing about the value is kept).
- `production_collector(settings, keyring=, environ=, request_id=, now=)` returns a `ProductionCollector`
  (`Callable[[Sequence[_Tenant]], ProductionObservations]`); `run_doctor(production=)` accepts either ready
  observations or that collector and calls it with the tenant directory it read for `audit-chain`, so one run
  records exactly one `PLATFORM_SCOPE_USED` event. `cli.py doctor` (composition root) builds the collector when
  `get_settings().env is Environment.PRODUCTION` with `os.environ`, the CLI key ring and the clock; `--db dev`,
  `test` or `e2e` switches the environment first, so the production checks never run under `--db`.
- Layering: `controls` stays a kernel module (imports `config`, `controls.release`, `db.lint`, `db.session`,
  `db.tables`, `db.migration_ops`); the key ring is consumed through its public `KeyRing` surface (`getattr` for
  the P2 accessor); no adapter type crosses in. DG-ARC-03: `get_settings` only in `cli.py`.

### Interfaces expected from the pending lanes (check their merges against these)

| Lane | Expected on merge | How the doctor consumes it |
|---|---|---|
| P2 (`sprint/l7`) | `Settings.security_hmac_secret_version: int \| None` with alias `EREV_SECURITY_HMAC_SECRET_VERSION`, required under `production`; `KeyRing.current_security_key_id() -> str` returning `security-hmac:<n>` for the version the process signs with; `KeyRing.security_event_key(<that id>)` serving 32 bytes | `snapshot_settings` reads the field (pin defined → checked, no WARN); `observe_key_provider` finds the accessor (provider collected → `key-version-pin` compares pin and identity). If P2 also moves `ANTHROPIC_API_KEY` to Secret Manager under `gcp`, `Settings._cross_field_rules` must stop requiring the setting for the `anthropic` provider, or the SAR-40 Anthropic warning stays unreachable through `Settings` (today it is: the rule refuses `anthropic` without the key) |
| P6 (`sprint/l8`) | module `erev_api.controls.recovery_preflight` (its presence marks the build as defining CFG-30); `EREV_RECOVERY_PROVIDER`, `EREV_BACKUP_URL`, `EREV_RESTORE_ADMIN_URL` read from the process environment (the CLI passes `os.environ`; a value that lives only in `.env` is not seen by the doctor, by design: no `.env` read beyond `Settings`) | `_DEFINING_MODULES` flips `recovery-provider` from WARN to checked; the predicate applies the CFG-30 rules P6's `resolve_recovery_provider` also applies (NATIVE/MANAGED, key-provider consistency, URL presence) |
| INT lane | `erev_api.db.tables.integration_connection` exported from `erev_api.db.tables` with columns `tenant_id`, `code`, `status` (`ACTIVE`/`DISABLED`), `base_url` (04 T-INT-01) | `observe_integration_connections` selects `code, status, base_url` per workspace; the unit test switches from `CollectorPending` to the column check when the table appears |

### SOP-1 / SOP-7 execution and audit inventory

| Check group | Runs where | Writes | Control marker |
|---|---|---|---|
| Five baseline checks (RLS, app role, triggers, audit chain, AI) | `erev doctor` from the CLI (`make doctor`; RB-02 / OPR-11 (3) hosted steps); no job, schedule or startup hook | one `PLATFORM_SCOPE_USED` security event (T-PLT-06) from the tenant-directory read; no `audit_event` (no row changes); no `control_execution` until T-PLT-39 (SOP-1) | none: REQ-CTL-005 has no designated CTL in 03 §4.1 (`CTL-036` covers RLS/lint through `test_rls_isolation.py`); M-PM-05 evidence |
| Eleven SAR-40 production checks | the same command under `EREV_ENV=production`, after the five | nothing further (the connection collector reuses the tenant directory; the catalogue collector opens one `erev_app` catalogue connection) | none; `release-stamp` overlaps `CTL-032`'s impact paths (`backend/erev_api/controls/**`) whose tagged test is lane P1's manifest work — not tagged from here |
| Related automatic checks elsewhere | REL-03 stamp at api/worker startup; UPL-05 `DEFUSEDXML` startup self-test; SCH-13 `partition_window_check` (24-month warning; lane P2) | their own logs / `engine_release` row | as owned |

### Fail-first evidence (measured)

- Module on `eb5546a` with the P4b tests added and the code unchanged: `1 error in 0.22s (exit 2)` (`.run/p4/p4b-fail-first-before.log`).
- CLI path on `eb5546a` with the new `doctor.py` in place but `cli.py` unchanged
  (`-k cli_doctor_composes`): `1 failed, 69 deselected in 0.85s (exit 1)` — under `production` the command printed only the five sentinel lines
  (`.run/p4/p4b-cli-fail-first-before.log`).
- After `e44227b`: `70 passed in 0.96s (exit 0)` (`.run/p4/p4b-fail-first-after.log`).

### Owed (explicitly unfinished; not a regression)

1. REL-07 unknown-setting-reference check and `tests/pg/test_doctor.py::test_rel_07_unknown_setting_reference`.
2. `--analyze <tables>` as `erev_owner` (DG-MK-perf-seed step 4).
3. Database evidence for the production path: the pg suite runs with `EREV_ENV=test`, whose database pair differs
   from `production`'s, so a pg test of `production_collector` needs either a supervisor-run production-mode
   process against a clone (OPR-11 (3)) or a pg test that forces the settings pair; `make doctor` exit 0 on dev
   (five checks) stays the SOP-6 evidence line; `make ci`, `make test-pg` in the lane's one chain under the lock.
4. P2 / P6 / INT wiring completes at their merges against the interface table above; `docs/guides/itgc-guide.md`
   "Deployment self-check"; SOP-1 `control_execution` producer for the doctor once T-PLT-39 exists.

### SOP-1 `record_execution` interface agreed with lane F-CLO (lane-eng-b2), 2026-09-19

Agreed as an interface only: the T-PLT-39 registry is not in P4's current dispatch; P4 builds to this shape when
the SOP-1 phase is dispatched, F-CLO builds nothing overlapping. Ownership: P4 — the T-PLT-39 revision (including
the FK for `close_checklist_item.control_execution_id`, `tables/close.py:105`, per the 0047 note), `tables/platform.py`
`control_execution`, `controls/evidence.py::record_execution`, `GET /control-executions`, `GET /releases` (API-R-52),
and the producers whose code exists (CTL-001/002/012/022/029/030/039/044); F-CLO — the producers for CTL-016
(CLO-6 lock execution, CLO-19 close run), CTL-019/020 (CLO-10), CTL-021 (CLO-14), CTL-024/025/026 (CLO-16/17).
Migration head: P4 takes it at the SOP-1 dispatch; F-CLO adds none.

```
record_execution(uow, *, control_id: str, run_ref_type: RunRefType, run_ref_id: UUID,
                 population_count: int, exception_count: int, result: ControlResult,
                 detail: Mapping[str, Any] | None = None, exceptions_file_id: UUID | None = None,
                 entity_id: UUID | None = None, book_code: str | None = None,
                 period_id: UUID | None = None) -> UUID   # the new row id
```

`engine_release_id` and `executed_at` are filled inside the helper (process release stamp, `uow.now`);
`RunRefType` is a `StrEnum` of the eight T-PLT-39 literals in `erev_api.enums`; `result` is the E-98
`ControlResult`. Validation inside the helper: `control_id` matches `^CTL-[0-9]{3}$` and exists in `controls.yaml`
(`ValueError`: a producer bug, not a Problem); `PASS` requires `exception_count == 0`; `FAIL` requires
`exception_count >= 1`; `NOT_APPLICABLE` requires `population_count == 0`; counts non-negative; `detail`
strict-JSON-serialisable — string object keys and finite numbers at every depth, objects inside arrays included
(Codex P4-S1-R1/R2, D-98 candidate 47) — and stored as given, no key normalisation. No unique index on
`(control_id, run_ref_type, run_ref_id)`: 04 specifies only
the non-unique `ix_control_execution__run` and an IM-A re-run appends a row. Per-control `detail` shapes belong to the
producer's lane. Supervisor rulings (2026-09-19, after `bb8c619`; principles P4 implements at the SOP-1 dispatch):
(a) an on-demand reconciliation (CTL-024/025/026) records against the reconciliation run's own row id with
`run_ref_type = RECONCILIATION_RUN` — an on-demand run creates a run row, and no execution row exists without a run
reference; (b) CTL-016 at lock time before CLO-19 exists binds to the `PERIOD_LOCK` approval request id with
`run_ref_type = PERIOD_LOCK`, and inside a close run (once CLO-19 exists) to the close run. The `RunRefType` enum
therefore carries `RECONCILIATION_RUN` and `PERIOD_LOCK`; relayed to lane F-CLO. `test_ctl_042_every_producer_records_execution`, when written, covers only producers whose code
exists on main at that time and lists the rest as pending on their lanes.

## Codex P4B-R1 (on merged main `c8899be`): diagnostics leaked credentials past URL userinfo

Finding: `redact` removed only DSN userinfo, so a collector or key-derivation exception carrying a
token query parameter, an `Authorization: Bearer` value or a `password=` assignment survived into the
native FAIL line (seven failing controls, canaries only; evidence `2026-09-19-p4b-doctor-c8899be.json`,
`2026-09-19-p4b-c8899be-cli-evidence.json`). RB-03 promises redaction, so this is an implementation
correction; no docs wording changed.

Correction `36afc54` (`controls/doctor.py`): `redact` takes the first line only and masks, as `***`,
DSN credentials, token / access_token / api_key / client_secret / secret / key style query, form and
assignment values (`=`, `:`, `=>`; bare or quoted), Authorization and Proxy-Authorization values (any
scheme), bare `Bearer <value>`, and PGPASSWORD / password / passwd / pwd / `EREV_*_(KEY|URL|SECRET|PASSWORD|TOKEN)`
/ `ANTHROPIC_API_KEY` assignments; 300-character bound. `diagnostic(exc)` (type name + redacted first
line) is all `_collect` records as a provenance error and all `observe_key_provider` records as the
probe detail. The regex shapes and mask follow lane P6's `recovery_preflight.DSN_CREDENTIALS` /
`KEY_VALUE_SECRET` (not on main yet): at P6's merge the two should become one helper — P6 importing
`erev_api.controls.doctor.redact` or both moving to a small `controls/redaction.py`; recorded here as
the consolidation point.

Fail-first (measured): on `c8899be` with the canary tests added, 20 failed / 75 passed, exit 1
(`.run/p4/p4b-r1-before.log`; the CLI test printed the Bearer canary verbatim); on `36afc54`, 95 passed in 1.16s, exit 0
(`.run/p4/p4b-r1-after.log`). Regression controls with the synthetic canary `P4B-SYNTHETIC-CANARY-0f9a`
(never a real credential): `test_p4b_r1_redact_removes_every_credential_form` (16 forms),
`test_p4b_r1_redact_keeps_useful_diagnostics` (6 diagnostics unchanged, incl. `KeyError: 'anthropic-api-key'`
and `EREV_KEY_PROVIDER=gcp requires …`), `test_p4b_r1_redact_keeps_only_the_first_line_and_bounds_length`,
`test_p4b_r1_collector_and_provider_diagnostics_are_bounded_and_safe` (predicate path: provenance error,
provider detail and FAIL lines), `test_p4b_r1_cli_stdout_never_carries_a_collector_credential` (actual Typer
stdout under production, exit 1). Gates: `make lint` exit 0; `make typecheck` exit 0; architecture + related
unit files 114 passed. The 60/60 predicate controls and the 16-check production composition are unchanged.
Codex's three `--db dev|test|e2e` cases under a hosted synthetic environment are, per the supervisor,
invalid hosted-to-local expectations and not regressions. Codex retests `36afc54`.

Erratum: the titles of commits `36afc54` and `ecef4f6` say 96 tests; the measured count is 95 passed (the
first-line case moved from the parametrised form list into `test_p4b_r1_redact_keeps_only_the_first_line_and_bounds_length`).
Commit messages are not amended under the lane rules; the counts above are the measured ones.

## Codex P4B-R1 retest (PRODUCTION-P4B-REDACTION-RETEST-36afc54; 83/86 + 0/9): structure, not patterns

Retest (SHA-256 `c55b8e9b0bb5e969df7c2d20de81e4a0a867b4e9cffb39735d20a2f8bc0e2989`): the seven original
failures closed at `36afc54`, but nine structured-message controls still leaked (`{"password": …}`,
`{"access_token": …}`, `{"Authorization": "Basic …"}`, `password="prefix …"` through `_collect`,
`observe_key_provider` and the actual Typer stdout): quoted JSON field names put a quote before the
separator and quoted multi-word values stop at whitespace. Supervisor ruling: for an arbitrary external
failure the FAIL line carries the exception TYPE plus a fixed, code-owned source context and no
free-form message text; free-form detail only under a rule that proves its safety (a code-owned
enumerated reason); a "permissive first line" is untrusted.

Docs first `d5351c0`: RB-03 "How the command collects" and DG-MK-doctor (rev 1.18 on this branch;
renumber at merge if main moved) state the rule. Correction `0d2aa71` (`controls/doctor.py`):
`_collect` records `<Type> while <attempt>` from the code-owned `_ATTEMPTS` per member for any
exception other than `CollectorPending`; `CollectorPending` takes a reason from `PENDING_REASONS`
(`PENDING_KEY_ID_ACCESSOR`, `PENDING_INTEGRATION_TABLE`) and refuses anything else, so the single
verbatim path cannot carry external text; the key-provider probe detail is `<Type> while deriving the
current security-hmac key`; a malformed provider key id is named, never echoed; the session-cookie
summary prints scheme and host only. The pattern helper (`redact`, `diagnostic`, the regexes) is
removed: the doctor prints no untrusted text, so no redaction is needed and none is relied upon. The
earlier P6 consolidation note is moot for the doctor (P6's `redact_diagnostics` stays the scripts'
helper for text they must print).

Fail-first (measured): against the `36afc54` module the rewritten test module fails at collection
(new names absent; exit 2, `.run/p4/p4b-r1b-before.log`); with the three new names shimmed onto that
module, all 24 P4B-R1 controls fail and the Bearer canary is visible in the failure output
(`.run/p4/p4b-r1b-before-shimmed.log`); on `0d2aa71`, 94 passed, exit 0 (`.run/p4/p4b-r1b-after.log`).
Controls (synthetic canary only): 17 untrusted messages — the original seven-control forms, Codex's four
structured forms, further JSON/quoted forms, the lane's quoted multi-word value (`secret = "two words …"`)
and JSON-quoted key (`{"key": "…", "note": …}`), and a two-line message — through `_collect`
(provenance error), `observe_key_provider` (probe detail) and the rendered FAIL lines; Codex's four plus
the lane's two through the actual Typer `doctor` stdout under production (exit 1, no canary, exact
type+attempt lines); `CollectorPending` refuses a non-code-owned reason; an impostor `RuntimeError`
subclass renders as type+attempt; a malformed key id is never echoed. Gates: `make lint` exit 0;
`make typecheck` exit 0; architecture + related unit files 114 passed; the 60/60 predicate controls and
the 16-check production composition are unchanged in behaviour (two message texts changed: the
malformed-key-id finding no longer echoes the id; the provider probe detail is type+attempt).

Branch note: `sprint/l15` could not fast-forward to main after `c8899be` (main moved while the four
record/correction commits were unmerged); the lane stays on its branch and the supervisor merges.
Codex retests `0d2aa71`.

Codex closure (PRODUCTION-P4B-FIXED-DIAGNOSTIC-RETEST-0d2aa71.md, SHA-256
`74b1ff3728aa5fd607d5bc61feb5bc2b16a8dfaef14608a63692d964bd4bb1a5`): P4B-R1 closed at `0d2aa71` — the
original 7 and the structured 9 disclosure cases pass; the 60 predicate controls pass; four added controls
pass (the exception `__str__` is never read; an unenumerated pending reason is refused; a malformed key id
is not echoed; cookie userinfo is omitted); raw 95/99 preserved (three qualified hosted-to-local
expectations and one obsolete assertion that demanded the now-suppressed free-form text). `c1bb4c3`
merges after the interim batch.

## P4c dispatch (2026-09-19 evening): SOP-1 registry, SOP-6 remainder, SOP-7 audit coverage — plan

Facts: main's migrations end at `0054` (P2 `0055`, C1b `0056` not landed) — the T-PLT-39 revision is
prepared in scratch and takes the head only when `0056` is on main; `tests/api/test_me.py` pins
`schema_revision == "0054"` and moves with it; no `sync_run` table on main (CTL-002 waits on the INT lane);
183 command operations in the committed OpenAPI; the lane databases `erev_rv_l15_*` do not exist yet
(provisioning asked of the supervisor for the 16:08 targeted DB runs).

| Item | Deliverable | When | Owner beyond P4 |
|---|---|---|---|
| SOP-1 1a | `RunRefType` (eight T-PLT-39 literals + `RECONCILIATION_RUN`, `PERIOD_LOCK`; 04 T-PLT-39 amended per the rulings, docs first), `controls/evidence.py::record_execution` to the F-CLO shape with helper-side validation, `schemas/controls.py`, unit tests, revision draft in `.run/p4/` | now (CPU) | — |
| SOP-1 1b | the revision (IM-A, RLS-T / RLS-TE on `entity_id`, FK `engine_release`, `close_checklist_item.control_execution_id` FK), `tables/platform.py control_execution`, `api/v1/controls.py` (`GET /control-executions`, `GET /releases`, `audit.read`), `make openapi`, `test_control_evidence_api.py`, `test_me` → `0057`, `test_migrations`, `test_rls_isolation[control_execution]` | when `0056` is on main | supervisor (head sequencing) |
| SOP-1 1c | producers with existing code: CTL-012 (`contracts/computation.py`), CTL-001/044 (imports commit), CTL-022 (`journals/summarise.py`), CTL-029/030 (`reports/framework.py`), CTL-039 (`platform/audit_jobs.py`); `test_ctl_042_every_producer_records_execution` (CTL-042 tag), `test_control_id_pattern_and_immutability` | with 1b | INT lane (CTL-002 `SYNC_RUN`); F-CLO (CTL-016/019/020/021/024/025/026) |
| SOP-6 2a | REL-07 as a sixth baseline check `setting-references` over schema `erev` functions (`current_setting('app.<name>')` outside {tenant_id, user_id, entity_scope, platform_scope, data_fix_ticket}); docs first (RB-03 row, DG-MK-doctor); `test_rel_07_unknown_setting_reference` (pg; `test_doctor.py` five → six lines) | now (CPU); pg in the chain | — |
| SOP-6 2b | `erev doctor --analyze <tables>` as `erev_owner` (owner engine; allow-listed schema-`erev` tables) | now (CPU); pg in the chain | — |
| SOP-6 2c | `itgc-guide.md` "Deployment self-check" | now | — |
| SOP-6 2d | DB evidence for the production doctor path: (A) pg test forcing the production settings pair onto `erev_test`, or (B) supervisor-run production-mode process against an OPR-11 clone; A proposed now, B at the hosted verification | chain / supervisor | supervisor (choice; B) |
| SOP-7 3a | `tests/support/audit_catalogue.py` (REQ-PLT-019 categories → handler action names; every command operation → handler + action or exemption class) and a CPU test that the catalogue is complete against the committed OpenAPI | now | — |
| SOP-7 3b | `test_ctl_038_every_command_route_writes_audit`, `test_denied_commands_audited` over the existing API fixtures; routes without a fixture and handlers without an audit event listed per owning lane | chain | feature lanes (handler fixes, fixtures) |

### P4c progress (2026-09-19 evening; all commits `if make lint`, `make typecheck`, architecture + related unit files)

| Commit | Item | Content | Evidence |
|---|---|---|---|
| `a7fa883` | SOP-6 2a–2c docs first | RB-03 sixth check `setting-references` (example line, table row) and the `--analyze` paragraph; DG-MK-doctor rev 1.19; itgc-guide "Deployment self-check" (heading enforced by `test_guides`) | lint 0; `test_guides` 3 passed |
| `82efb11` | SOP-6 2a, 2b code | `setting-references` (05 REL-07) as the sixth baseline check: `observe_setting_references` over `pg_proc`, `referenced_settings` (non-identifier-shaped names reported as unparsable, never echoed), `setting_references` failing per function and setting outside `DOCUMENTED_SETTINGS`; `analyze_tables` + `erev doctor --analyze <tables>` as `erev_owner`, no check, unknown table exit 2; `tests/pg/test_doctor.py` `CHECKS` six + `test_rel_07_unknown_setting_reference` (probe trigger function; runs in the chain) | new `tests/unit/test_doctor_baseline_checks.py` 11 tests (fail-first: collection error before the code); doctor unit modules 105 passed; lint 0; typecheck 0; architecture + related 114 passed |
| `dc3febd` | SOP-1 1a docs first | 04 T-PLT-39 `run_ref_type` gains `RECONCILIATION_RUN` and `PERIOD_LOCK` (supervisor rulings); Python mirror `erev_api.controls.evidence.RunRefType` named; 04 rev 1.18 on the branch | lint 0; drift test 5 passed |
| `afa5941` | SOP-1 1a code | `controls/evidence.py` (`RunRefType`, `ExecutionRecord`, `validate_execution` with the F-CLO rules); `schemas/controls.py` (`ControlExecutionOut`, `ReleaseOut`); `record_execution`'s insert, the table, routes and producers wait for 0055/0056 (revision draft `.run/p4/sop1/0057_sop_1_control_execution.py`) | `tests/unit/test_control_evidence_validation.py` 23 tests (fail-first: collection error before the module); lint 0; typecheck 0; architecture + related 114 passed |
| `65255eb` | SOP-7 3a | `tests/support/audit_catalogue.py` (`CATEGORIES`, `ROUTES`, readers) and `tests/unit/test_audit_catalogue.py` (6 tests) | lint 0; typecheck 0; architecture + related + module 120 passed |

`RunRefType` lives in `controls/evidence.py`, not `erev_api.enums`: `test_dg_arc_09_enums_match_data_model`
asserts that module's StrEnums equal exactly the 04 §3 E-enums, and T-PLT-39 `run_ref_type` is text with a
check. Lane F-CLO was told the import path.

SOP-7 catalogue inventory (183 command operations of the committed OpenAPI): 162 `audit_event` routes, of which
133 carry the handler's action literal(s) and 29 are inventoried without a known action (the database walk
establishes each; a route that writes none is a handler defect for its owning lane): `account_mappings_publish`,
`account_mappings_submit`, `account_mappings_test`, `approvals_withdraw`, `audit_events_verify`,
`combination_groups_submit`, `combination_suggestions_dismiss`, `contracts_distinct_review`,
`contracts_submit_activation`, `estimate_versions_submit`, `estimate_versions_update`,
`estimate_versions_withdraw`, `import_mapping_profiles_publish`, `import_mapping_profiles_submit`,
`import_mapping_profiles_test`, `jobs_cancel`, `pob_template_versions_publish`, `pob_template_versions_submit`,
`policies_presets_legacy_parity`, `policies_publish`, `policies_submit`, `policies_withdraw`,
`products_propose_principal_agent_change`, `roles_propose_change`, `rule_set_versions_publish`,
`rule_set_versions_submit`, `saved_views_create`, `saved_views_delete`, `saved_views_update` (several of these
build their action name dynamically from the state transition, so no literal exists to grep); 11
`security_event` routes (login, logout, MFA, tenant selection, password reset, OAuth token, `me` MFA and
password); 1 `provisioning` (`operator_tenants_create`); 9 `query` routes that compute or mark and write nothing
by design (`contract_events_preview`, `estimate_versions_preview`, `rule_sets_evaluate`, `explain_verify`,
`session_lookup_invitation`, and the AUD-OPS `me_notifications_read`, `me_notifications_read_all`,
`me_notification_preferences_put`, `me_preferences_update`). The REQ-PLT-019 category names are the handlers'
(`sod_exception.request`, `period.start_close`, `event_submission.request_void`, `registry_version.update`,
`journal_run.request_export`, `support_grant.request`), not the SOP-7 examples where those differ; "AI proposal
lifecycle" is pending on lane F-AIX (no `ai_proposal` literal on this build).

Question for the supervisor (SOP-7): the route rule "every POST/PUT/PATCH/DELETE other than the five named
routes writes at least one `audit_event`" meets nine command-shaped operations that write nothing by design
(previews, evaluation, explain verify, invitation lookup, and the 04 §1.7 AUD-OPS read markers and personal
preferences). Proposed: the database walk treats the catalogue's `query` class as an explicit exemption list
(named in the record and in the test's failure message), or the spec's exemption list is amended. Also open:
provisioning of `erev_rv_l15_test`; the 2d choice (A recommended); 0055/0056 landing for SOP-1 1b/1c.

### SOP-1 1b: validated draft staged (not committed; waits for 0055 and 0056)

Prepared in the working tree at `eeb0f77`, validated, exported to `.run/p4/sop1/` (`sop1-1b-tracked.patch`,
`new/**`, `README.md` with the apply steps) and the tree restored to clean. Content: `tables/platform.py`
`control_execution` (T-PLT-39 columns; `book_code` as the E-02 type; `result` as `control_result`) and its
export; `controls/evidence.py::record_execution` (validate, resolve the running release as the journal
summariser does — `release-mismatch` when none —, insert with `uow.now`, return the row id; AUD-FACT, no
audit event of its own); `api/v1/controls.py` (`GET /control-executions` with filters `control_id`,
`run_ref_type`, `result`, `from`, `to`, sort `-executed_at`; `GET /releases` from T-PLT-38 with
`gate_results`; both `audit.read`) registered after `audit.router`; the revision `0057_sop_1_control_execution`
(`create_tenant_table` with the three checks and two non-unique indexes, `add_global_fk engine_release`,
tenant FKs to `legal_entity`, `period`, `file_object`, `apply_class IM-A`, `enable_rls RLS-TE entity_nullable`,
the 0047 `close_checklist_item.control_execution_id` FK; `down_revision` set to `0056` in the staged copy);
`tests/support/rows.py` `control_execution_values` / `control_execution_row` so
`test_ctl_036_cross_tenant_isolation[control_execution]` is parametrised; `tests/domain/platform/test_control_evidence.py`
(`test_control_id_pattern_and_immutability`: `CTL-50` → 23514, `UPDATE` as `erev_app` → 42501;
`test_record_execution_round_trip`); `tests/api/test_control_evidence_api.py::test_req_ctl_002_query_and_export`
(range and control filter newest first, item keys, viewer 403 `forbidden`, `GET /releases`); `test_me`
`schema_revision` → `0057`; `test_migrations` head → `0057` with the function count to re-measure after
0055/0056. Validation measured with the draft applied: ruff clean; mypy strict clean (566 files); `make openapi`
regenerated `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` (+883 lines); architecture + unit
(`test_control_evidence_validation`, `test_audit_catalogue`, makefile targets, controls report) 126 passed;
the three database modules collect (138 tests incl. the new isolation case). The producer walk
`test_ctl_042_every_producer_records_execution` and the producers themselves are 1c.

### SOP-1 1c: producer wiring drafted on top of 1b (staged, not committed)

Wired in the staged draft (`.run/p4/sop1/sop1-1b-1c-tracked.patch`): CTL-039 in
`audit/verify.record_tenant_verification` (one row per verification; population = events checked; a FAIL is one
exception; detail trigger and first failing sequence); CTL-012 in `domain/contracts/compute_job` (PASS per
non-replayed persisted computation with `obligation_count` as the population; FAIL with one exception per
refused computation, in `_refused`); CTL-001 and CTL-044 at the end of `domain/imports/commit.commit_upload`
(population = rows loaded + quarantined, exceptions 0 — rejected rows are the control working, carried in
detail; CTL-044 population 1 with uploader and approver ids in detail); CTL-022 per journal batch in
`domain/journals/summarise` (population = batch lines; `entity_id`, `book_code`, `period_id` set; totals in
detail); CTL-029 and CTL-030 at report-run success in `domain/reports/framework` (CTL-029 population 1 with
the output hash; CTL-030 population = tie-outs, exceptions = tie-out FAILs, NOT_APPLICABLE when none).
Exception counts count control failures, not handled rejections (F-CLO rule). Not wired: CTL-002 `SYNC_RUN`
(INT lane; no table on main) and the F-CLO controls. Tests in the draft: `test_ctl_042_verification_producer_records_execution`
(CTL-042 tag; the CTL-039 producer through `record_tenant_verification`), plus `support.rows.insert_engine_release`
and a stamped release in `tests/pg/test_doctor.py`'s workspace fixture, because `record_execution` raises
`release-mismatch` where no release row exists. Validation with the combined draft applied: ruff clean;
mypy strict clean (566 files); architecture + unit 107 passed; the seven database modules collect (39 tests);
no database test run. Expected fallout to fix first when the lane database exists: verification and import
fixtures without a stamped release (`test_audit_verification.py`, `test_jobs.py`, `test_job_monitoring.py`,
`close/test_period_states.py`, the import world). The full producer walk named by SOP-1 extends the CTL-039
test once each producer's scenario runs against the database.

### Supervisor decisions on the P4c plan (2026-09-19 evening)

Plan approved as written. 2d = option A now (a pg test forcing the production settings pair onto the
test database the fixture is configured with — `erev_test` on main's chain, `erev_rv_l15_test` on this
lane's; never a hard-coded database name, never dev `erev`); option B (a supervisor-run production-mode
process against an OPR-11 clone) at the hosted verification, recorded as the remaining evidence.
Databases `erev_rv_l15_{dev,test,e2e}`: creation is forbidden to code and agents (DG-FORBID-03,
DG-ENV-14), so provisioning is Ray-side (values-free list); no `psql` / `createdb` attempt; until then the
lane stays CPU-only, keeps the pg tests collected for its chain, and marks database-bound items
"not run — databases not provisioned". Sequencing confirmed (record → SOP-6 → SOP-1 1a → SOP-7 3a →
SOP-1 1b/1c when 0056 is on main → DB tests in the chain or under the 16:08 amendment). SOP-7 per-route
inventory returns missing-fixture routes and non-auditing handlers per owning lane. Lane F-CLO accepted
`RunRefType` in `controls.evidence` (their record `8f1ae77`).

### Codex P4C-S6 review (PRODUCTION-P4C-SOP6-REVIEW-82efb11; 19/31): two corrections

| Finding | Correction | Fail-first (measured) | Commit |
|---|---|---|---|
| P4C-S6-R1 — the REL-07 parser matched one spelling of `current_setting('…')` by substring, certified an empty extraction as OK (false OK through `run_doctor` on `CURRENT_SETTING ('app.unlisted',true)`), accepted the documented prefix of `'app.tenant_id' \|\| '_shadow'`, and mistook comments for references (8 missed variants, 2 false positives) | `referenced_settings` lexes the source (PostgreSQL `--` and nested `/* */` comments; `'…'` with doubled quotes; `E'…'` with `\n`-style, `\xhh`, `\ooo`, `\uxxxx`, `\Uxxxxxxxx` escapes; `$tag$…$tag$`; `"quoted identifiers"` exact; bare identifiers case-folded), finds every `current_setting` call followed by `(` and takes the FIRST argument by nesting-aware boundary: one string literal → the name (documented OK / unknown FAIL / non-identifier `<unparsable>`, never echoed); anything else → `<unresolved>`, reported as "passes current_setting an argument that is not a single string literal (05 REL-07)" naming the function only | parsing table 5 → 32 cases (Codex's eight variants, more unresolved shapes, the two comment-only positives plus a nested comment, string contents, another-case quoted identifier, a look-alike name), the unresolved predicate finding, the composition control (real collector + predicate → sixth result FAIL). With the new constant shimmed onto the regex parser: 23 of 32 REL-07 controls failed (`.run/p4/p4c-s6-r1-before-shimmed.log`); after: doctor unit modules 130 passed | `50f460b` (lint 0; typecheck 0; architecture + related 110 passed) |
| P4C-S6-R2 — `doctor --analyze` caught every `ValueError` from `analyze_tables`, including execution-layer ones, and printed `str(exc)` (an inert adapter raising `ValueError('password=<canary>')` echoed it verbatim, exit 2) | `analyze_tables` validates every name against the metadata allow-list before any SQL (`UnknownTable(table)`: the caller's argument, safe to print), plans all statements first, and turns any execution failure — including a failed `begin()` — into `AnalyzeFailed(index, count, exception_type)` with the message dropped (`from None`); the CLI prints "unknown table <name>" exit 2 or "ANALYZE failed at table i of n: <Type>" exit 1, disposes in `finally`, never `str(exc)` of an arbitrary exception, no credential-pattern filter | with the two names shimmed onto the old module: 3 of 4 analyze controls failed, the CLI printing `password=<canary>` (`.run/p4/p4c-s6-r2-before.log`); after: 132 passed. Preserved: four ANALYZE statements in order; mixed / semicolon / schema-qualified / foreign-schema / newline names refused before `begin()`; owner role; disposal; no doctor path; canary case exits 1 with exactly "ANALYZE failed at table 1 of 1: ValueError" | `fbaf931` (lint 0; typecheck 0; architecture + cli-health + controls-report 82 passed) |

Codex retests `fbaf931`.

### SOP-7 ruling D-98 (20) applied

Docs first `e99f331`: BUILD_SPEC SOP-7 `test_ctl_038_every_command_route_writes_audit` defines its exemptions
by class — (a) the five named routes, (b) stateless evaluations that return a result and persist nothing
(preview, evaluate, explain-verify), (c) the 04 §1.7 AUD-OPS personal read markers and preferences —
enumerated as the catalogue's `query` class, each named in the failure message and here; the walk asserts a
`query` operation persists nothing but the §1.7 personal rows (zero `audit_event`, zero other writes);
`POST /session/invitations/lookup` is not exempt. Edited in the source `docs/build-spec/11-foundation-platform.md`,
header `00-header.md` rev 1.4 with its (oldest-first) revision-log row, `docs/BUILD_SPEC.md` regenerated by
`merge_buildspec.py`. `check_merged.py` reports a pre-existing coverage FAIL "SOP-3: 5 unwaived modules"
(lane P5's item), unrelated to this edit. Catalogue `afde4db`: `QUERY_EXEMPT` pins the eight exempt operations
(`contract_events_preview`, `estimate_versions_preview`, `rule_sets_evaluate`, `explain_verify`,
`me_notifications_read`, `me_notifications_read_all`, `me_notification_preferences_put`, `me_preferences_update`);
`test_d_98_20_query_class_is_exactly_the_ruled_exemptions` holds the class to that set. Inventory now: 162
`audit_event` (133 with known actions, 29 unverified), 12 `security_event`, 1 `provisioning`, 8 `query`.

Handler-fix list per owning lane (SOP-7; returned, not fixed here): **F-ADM** — `session_lookup_invitation`
(`auth/invitations.find_invitation`) raises `not-found` and writes no `security_event` on an unknown, expired or
malformed token; D-98 (20) requires one (a new E-79 kind, e.g. an invitation-token failure), none on success.
The 29 unverified `audit_event` routes are assigned to their owning lanes by the database walk.

### Codex closure of P4C-S6-R1 and P4C-S6-R2 at `038cb8e` (recorded verbatim)

`PRODUCTION-P4C-SOP6-RETEST-038cb8e.md` (SHA-256 `7253518d14157644…`; manifest
`source-observations/p4c-sop6-038cb8e/MANIFEST.json`, SHA-256 `ea55f8323bf9cc9a…`), conclusion: "close the
original P4C-S6-R1 and P4C-S6-R2 implementation findings at exact committed
`038cb8e588397ca62933fb57f8d7289f5b18b43b`. The unchanged original probe passes 31/31, resolving all 12
original failures; independent additional controls pass 54/54, and a separate unsupported-literal boundary
probe passes 4/4. No expectation or original input was changed, no compatibility adapter was needed, and the
original 19/31 raw result remains intact. This is bounded CPU evidence, not database, PostgreSQL
parsing/execution, hosted-doctor or SOP7 integration acceptance." Supervisor's summary: four Unicode-escape /
adjacent-literal controls return unresolved and FAIL safely (no full PostgreSQL grammar certification claimed);
native ANALYZE / CLI controls refuse invalid names before transaction entry, redact fake driver-message
canaries at begin / enter / statement / exit, retain safe positions and types, select the owner role and
dispose; the P4B section is byte-identical to `0d2aa71`; the historical 95/99 stands.

### SOP-7 — explicit OPEN implementation items (Codex qualification; matrix clauses moved into this record, see below)

1. The spec-named `backend/tests/domain/platform/test_audit_coverage.py` does not exist yet; the CPU catalogue
   tests live in `tests/unit/test_audit_catalogue.py`. Preference (P4): create the spec-named module as the
   database-walk home, importing `tests/support/audit_catalogue.py` (no rename of the spec path), when the lane
   database makes the walk runnable; the unit module keeps the CPU completeness tests.
2. `session_lookup_invitation` failure-event writing is pending with lane F-ADM (a failed lookup must write a
   `security_event`; the handler raises `not-found` only today).
3. No route-audit / no-write runtime walk has been executed (`test_ctl_038_every_command_route_writes_audit`,
   the `query`-class no-write assertion, `test_denied_commands_audited`): needs the lane database —
   "not run — databases not provisioned".

Practice note (supervisor, 2026-09-20): `docs/reviews/loop/prod/readiness-matrix.md` is the docs lane's governed
document — its generator rewrites it on main (COMMIT 18); lanes record their state in their own record and report
it, and the docs lane stamps the matrix. The three "Lane P4 state 2026-09-20" clauses this lane appended to the
SOP-7, G9 and SAR-40 rows in `8c862b6` are therefore superseded: at the merge main's matrix wins textually and the
docs lane carries the three OPEN items from this record. `8c862b6` stays as committed (no history rewriting); no
further matrix edits on `sprint/l15`. Item (1) preference accepted by the supervisor: create the spec-named
`backend/tests/domain/platform/test_audit_coverage.py` importing the catalogue when the lane database exists.

Update 2026-09-20 (F-ADM): the SOP-7 handler item for `session_lookup_invitation` is implemented on lane F-ADM's
`sprint/l22-fadm` `b5e8352` (docs `8e53a44`, 04 rev 1.19): a failed lookup or acceptance (malformed, unknown,
expired, used or inactive token) writes `security_event` kind `INVITATION_LOOKUP_FAILED` (outcome FAILED,
anonymous caller, detail `{"reason", "route"}`, own identity transaction after the `tenant_directory` read); a
successful lookup writes nothing else. Catalogue `7842008` lists the kind on `session_lookup_invitation` and
`session_accept_invitation` conditionally on the build defining it, so the completeness test holds before and
after F-ADM's merge. Question returned to the supervisor: F-ADM's enum revision is numbered `0055`, the slot the
head sequencing reserved for lane P2 (`0055`) ahead of C1b (`0056`) and P4's `0057`; the numbers need reconciling
before either merge.

Ruling 2026-09-20 (supervisor): the collision is resolved by sequencing, not renumbering on this branch. F-ADM's
`ALTER TYPE security_event_kind ADD VALUE` revision moves to `0058` (down_revision `0057`) at F-ADM's merge, after
P2 `0055`, C1b `0056` and this lane's SOP-1 `0057`. The staged patch under `.run/p4/sop1/` and its head pins
(`0057_sop_1_control_execution.py`, `down_revision = "0056"`) stay exactly as drafted. Lane idle until 0055/0056
land on main or the Ray-side `erev_rv_l15_*` databases exist.

### Matrix restored to main; the three `8c862b6` clauses carried here (2026-09-20)

Supervisor slice: the read-only merge-tree preview of `sprint/l15` into main `7b4ba7f` conflicts in
`docs/reviews/loop/prod/readiness-matrix.md`. The matrix is the docs lane's governed document — lanes never edit
it — so this lane's copy is restored to main's version exactly (`git show 7b4ba7f:… >` the file; `git diff
7b4ba7f -- docs/reviews/loop/prod/readiness-matrix.md` empty), and the three "Lane P4 state 2026-09-20" clauses
that `8c862b6` appended to the SOP-7, G9 and SAR-40 rows live only here from now on. The docs lane stamps the
matrix from the supervisor's messages. The clauses as they stood on the branch:

- **SOP-7 row.** Lane P4 state 2026-09-20 (record `docs/reviews/loop/prod/P4-doctor.md`): catalogue
  `tests/support/audit_catalogue.py` + CPU tests `tests/unit/test_audit_catalogue.py` on l15 `65255eb`/`afde4db`;
  D-98 (20) exemption classes in BUILD_SPEC `e99f331`. OPEN implementation items (Codex qualification at
  `038cb8e`): (1) the spec-named `backend/tests/domain/platform/test_audit_coverage.py` does not exist yet — to be
  created as the DB-walk module importing the catalogue when the lane database exists; (2)
  `session_lookup_invitation` failure `security_event` pending with F-ADM (since implemented on F-ADM `b5e8352`;
  listed conditionally by `7842008`); (3) no route-audit / no-write runtime walk executed (needs the lane database).
- **G9 row.** Lane P4 state 2026-09-20 (record `P4-doctor.md`): SAR-40 predicates, collectors and CLI composition
  merged (`c8899be`, Codex-closed P4B-R1 at `0d2aa71`); REL-07 `setting-references` sixth check and `--analyze` on
  l15 `82efb11`, Codex P4C-S6-R1/R2 closed at `038cb8e` (`PRODUCTION-P4C-SOP6-RETEST-038cb8e.md`: original probe
  31/31, added controls 54/54). OPEN: the REL-07 pg test and the production-path pg test (2d option A) are
  collected, not run — databases not provisioned.
- **SAR-40 row.** Lane P4 state 2026-09-20: predicates and collectors merged `c8899be`; DB evidence open (see G9).

Since those clauses: `c1bb4c3` merged as main `ab237e5`; the SOP-6 / SOP-1 1a / SOP-7 commits after it stay on
`sprint/l15` for the merge after P2 `0055` and C1b `0056` (position after P5 in the merge order). Alembic: the
staged 1b/1c revision "`0057` down `0056`" is provisional — the supervisor assigns the final number at merge
(provisional sequence P2 `0055` → C1b `0056` → F-ADM `0057`/`0058` → P4 SOP-1 `0059` → F-LMG `0060` → F-SNP
`0061`); it stays staged as drafted and is not renumbered on the branch.

### Codex P4-S1-R1 / P4-S1-R2 (PRODUCTION-P4-SOP1-VALIDATION-1e1d664; raw 52/56; D-98 candidate 47)

Codex reviewed `1e1d664` / code `afa5941` (validator, schema and unit test byte-identical between them; report
SHA256 `fcb53d87…`, manifest `f8640a2c…`, 8 artifacts): the original admitted fixtures, all 19 producer refusal
inputs and message predicates, the ten reference types, books, counts/results, registry lookup and both
output-schema field sets pass; four newly labelled negative assertions fail across two findings on the `detail`
contract (contract paragraph above and the `evidence.py` docstring, both amended docs-first in this slice).

- **P4-S1-R1.** `json.dumps(given)` was permissive: otherwise-valid CTL-039 / AUDIT_CHAIN_VERIFICATION /
  population 120 / exceptions 0 / PASS inputs whose detail carried `{"totals": {"value": float("nan")}}`,
  `float("inf")` or `float("-inf")` were accepted, while strict JSON (`allow_nan=False`) refuses them. Ruling:
  non-finite numbers are rejected anywhere in detail — recursively, inside arrays included — with the promised
  `ValueError`; finite nested numbers stay valid. Helper validation ahead of the T-PLT-39 `jsonb` persistence.
- **P4-S1-R2.** The string-key check covered the outer mapping only: `{"counts": {1: "first", "1": "second"}}`
  was accepted, serialised both keys as `"1"`, and a round trip kept one entry — against the stored-as-given /
  no-normalisation rule. Ruling: non-string object keys are rejected recursively, objects inside arrays included;
  nested all-string-key positives stay valid.
- **Not introduced (ruling).** No `exception_count <= population_count` rule: FAIL with population 0 / exceptions 1
  stays admitted under the documented rule, now pinned by `test_fail_with_empty_population_stays_admitted`.

Fail-first on `ded49e8` code (evidence.py differing by docstring only; `.run/p4/s1/probe_ded49e8.py`, log
`.run/p4/s1/fail-first-ded49e8.log`): Codex's four exact inputs and three added negatives (non-finite inside a
nested array, non-string key in an object inside an array, top-level NaN) all ACCEPTED — 7 wrong of 11 cases, the
four positives valid; the amended unit file 8 failed / 25 passed (`fail-first-tests-ded49e8.log`).

Fix (`controls/evidence.py`): `_check_detail` walks mappings and lists/tuples below the top level before
`json.dumps(given, allow_nan=False)`; fixed code-owned messages `detail must not contain non-finite numbers` and
`detail nested objects must have string keys` (no key or value text echoed); the top-level message and every other
refusal message are unchanged. Tests (`tests/unit/test_control_evidence_validation.py`): the eight refusal cases
above in the producer-bug table; `test_detail_is_strict_json_at_every_depth_and_stored_as_given` (finite nested
numbers, nested all-string keys, objects inside arrays, strict-JSON round trip equal to the input, key order kept);
`test_fail_with_empty_population_stays_admitted`. After the fix (`after-fix.log`): probe 0 wrong of 11; unit file
33 passed; `make lint` exit 0; `make typecheck` exit 0 (mypy 564 files, tsc); architecture + lane unit files 247
passed. Codex retest requested on the commit reported to the supervisor with Codex's counterexamples unchanged.

### Codex P4-SOP7-R1 (PRODUCTION-P4-SOP7-CATALOGUE-REVIEW-1e1d664; 28/30; D-98 candidate 49)

Codex reviewed the catalogue at `1e1d664` by source and AST only (report SHA256 `68c91334…`, manifest
`a3fd8c6a…`, 11 artifacts): the inventory of 183 operations / 14 categories is complete against the committed
OpenAPI, the router decorators and router inclusion; 28 of 30 observations pass; the two failures are one issue.
`contract_events_preview` (`api/v1/events.py` → `domain/contracts/events.py::request_preview`) and
`estimate_versions_preview` (`api/v1/estimates.py` → `domain/contracts/estimates.py::request_preview`) were
classified `query` / "no row changes", yet both call `uow.defer(CONTRACT_COMPUTE, PREVIEW | ESTIMATE_PREVIEW)`,
which inserts a `job` row in the command's transaction (`jobs/registry.py::insert_job`) with dispatch registered
after commit, and `run_command` commits — against BUILD_SPEC SOP-7's condition (zero writes other than the
personal rows) and 04 T-PLT-27 AUD-OPS (the commands that start and finish jobs are audited). Codex also asked
that the persistence boundary be explicit: every `run_command` path, the query routes included, writes an
`idempotency_record` row, while the SOP-7 wording excepted only the personal rows.

Ruling (supervisor, 2026-09-20; D-98 candidate 49): both previews leave the stateless-query exemption — they are
job-starting commands in the audited class and their audit evidence is the job-start event; the exemption is not
widened and exact-set catalogue tests are not proof (only the walk is); the routine `idempotency_record` write is
stated in SOP-7 as an explicit AUD-OPS infrastructure allowance without exempting queued work. Cross-owner: whether
`insert_job` on the preview path emits the job-start `audit_event` is lane P2's (jobs registry) to confirm or add
— routed by the supervisor as P2's post-merge slice; this lane touched no worker or jobs file.

Applied, docs first: `docs/build-spec/11-foundation-platform.md` SOP-7 — class (b) no longer names previews; the
walk's persistence boundary is explicit (the `idempotency_record` row is the only infrastructure write allowed on
every path; a queued `job` row is not routine infrastructure); the two previews are named as job-starting commands
in the audited class with the job-start `audit_event` as evidence (P2 to confirm or add); the exemption is not
widened and the exact-set unit test is a declaration, not proof. Header `00-header.md` rev 1.5 with its
revision-log row; `docs/BUILD_SPEC.md` regenerated by `merge_buildspec.py` (`--check` equal). Catalogue
`tests/support/audit_catalogue.py`: `_job_start` routes for the two previews (`audit_event`, no action literal
claimed, note naming the job-start event and P2), `JOB_STARTING` constant, `QUERY_EXEMPT` reduced to six
(`rule_sets_evaluate`, `explain_verify`, `me_notifications_read`, `me_notifications_read_all`,
`me_notification_preferences_put`, `me_preferences_update`), module docstring stating the boundary. Tests
`tests/unit/test_audit_catalogue.py`: `test_d_98_20_…` pins six and disjointness from `JOB_STARTING`, its docstring
now says the pin is a declaration; new `test_d_98_49_job_starting_previews_are_audited_not_exempt`; the inventory
test names the two previews among the unverified routes (bound 31). Inventory now: 164 `audit_event` (133 with
known actions, 31 unverified — the 29 listed above plus the two previews), 12 `security_event`, 1 `provisioning`,
6 `query`. Gates: catalogue tests 8 passed; `make lint` exit 0 (after `ruff format` of the catalogue);
`make typecheck` exit 0 (mypy 564 files, tsc); architecture + lane unit files 248 passed.

No action (from the same review): the classes 162 → 164 `audit_event` / 12 / 1 / 6 are confirmed; the 29
audit routes without a known action and the AI-proposal category stay pending; the conditional
`INVITATION_LOOKUP_FAILED` registration behaves as declared (actual emission unverified);
`test_audit_coverage.py` and all durable-emission acceptance remain unfinished and Ray-side.

Update 2026-09-20 (supervisor slice): the `ded49e8` restore wrote main `7b4ba7f`'s matrix, but the merge base of
`sprint/l15` and main is older (`c1bb4c3`), so both sides differed from the base and the merge preview still
conflicted. The branch copy of `docs/reviews/loop/prod/readiness-matrix.md` is now byte-identical to the merge-base
version (`git show c1bb4c3:… >` the file; `git diff c1bb4c3 -- …` empty), so this side reads as unchanged and the
merge takes main's current matrix. The three `8c862b6` clauses remain carried in the section above.

### Codex closures of P4-S1-R1/R2 and P4-SOP7-R1 (recorded verbatim from the supervisor, 2026-09-20)

- **P4-S1-R1 / R2 CLOSED at exact `232d3a8b`** — `PRODUCTION-P4-SOP1-CORRECTIONS-RETEST-232d3a8.md` (SHA256
  `e96ac94b…`), manifest `9f5eb120…`: original 56/56 (was 52/56), focused nested-array / finite controls 6/6;
  NaN / ±Infinity and non-string nested keys refuse; string keys and finite JSON round trips preserved; all 19 old
  refusals unchanged; FAIL population 0 / exceptions 1 remains valid; pure validator only — no DB record / route /
  producer-emission acceptance.
- **P4-SOP7-R1 CLOSED at exact `86585ccc`** — `PRODUCTION-P4-SOP7-CLASSIFICATION-RETEST-86585cc.md` (SHA256
  `a49fa3fd…`), manifest `68ea81c3…`: 26/26 focused source / catalogue checks; same 183 IDs / methods / paths and
  14 categories; counts 164 audit / 12 security / 1 provisioning / 6 query; 133 known actions unchanged; unknown
  29 → 31 = exactly the two previews, both excluded from `QUERY_EXEMPT`; the idempotency-only allowance does not
  exempt job rows; the same-transaction job-start audit remains required — P2's emission and the actual audit walk
  stay open (assignment acknowledged, no duplicate producer).

### Merge of `cacff77c` (supervisor, 2026-09-20)

- main `9b611133` = "Merge lane P4 (sprint/l15 cacff77c)" onto `f4df47ef` via merge-revrows.sh (row-union clean).
  Resolver renumbering: the 04 T-PLT-39 revision row → **1.21** (branch said 1.18); the dev-guide SOP-6 row →
  **1.23** (branch said 1.19). Post-merge on main: lint OK; typecheck OK; engine + unit 2,086 passed / 1 xfailed /
  0 failed; release selection 220/220; governed-docs revision test passes (`.run/supervisor/lane-merge/P4-cacff77c/`).
- Status vocabulary: merged, not gate-measured — the integrated wrapped batch on the COMMIT 21 head measures it
  (tests/pg/test_doctor.py REL-07 cases run there).
- Not this lane's to fix: the merge left a duplicate P4B-R1 dev-guide log row (1.23) and a second 1.19 beside
  F-WEB-R's — resolver defect corrected docs-first in COMMIT 21 by the docs lane; DG-MK-doctor inline reference
  reads rev 1.23; 04 references read 1.21.
- Follow-up for the SOP-1 1b/1c slice (touches evidence.py anyway): the `RunRefType` docstring cites
  "04 T-PLT-39 run_ref_type (rev 1.18)" — update to the merged 1.21 (the mirror test splits on "(rev", so it is
  unaffected); check the staged 0057 revision docstring and `.run/p4/sop1/README.md` for the same 1.18 reference.

### F-CLO migration notice (lane-eng-b2, 2026-09-20) and the numbering ruling

- F-CLO's sprint/l18 carries `0055_clo_6_reconciliation_period_lock_id.py` (revision "0055", down "0054"; D-98 63:
  UPDATE(period_lock_id) grant + re-rendered `tg_reconciliation__transition`; no table/column/enum). Its number
  collides with P2's slot in the supervisor's provisional sequence; flagged to the supervisor for a slot ruling at
  F-CLO's merge. No content dependency with T-PLT-39. SOP-1 revision remains staged provisional ("0057 down
  0056") and is serialised after the main head the supervisor names, with head pins re-measured in that commit.
- F-CLO confirmed: holds "0055 down 0054" until the supervisor rules the final number at its merge (file, revision and
  both head pins renumbered in that commit); no content dependency confirmed on both sides (0055 touches only
  erev.reconciliation).
- Supervisor ruling (2026-09-20): Alembic **0055 = P5** (`0055_engine_release_validation_level` on 0054, on
  sprint/l12-p5;
  P5 merges right after group 2). F-CLO renumbers 0055 → **0056 on 0055** in its merge-prep slice after P5 lands.
  Then, in merge order, each migration-bearing lane takes its number at its merge-prep slice: P2 and C1b (both
  deferred — P2's chain aborted on a lane test; T1F red), F-ADM (two revisions), P4 SOP-1, F-LMG, F-SNP. P4's exact
  number is not fixed (depends on P2's position): hold the provisional "0057 down 0056" unchanged; re-measure the head
  pins only when the supervisor names the number and the head.

### SOP-1 merge prep on main `69ee7324` (supervisor dispatch, 2026-09-20)

Assignment: the SOP-1 migration becomes **0057 on 0056** (P5 `0055` on main; F-LMG `0056` at merge prep, landing
before P4); merge main `69ee7324` into `sprint/l15`; confirm SOP-1's state; list the governed-document rows
carried; captured gate statuses; one commit inside the lint guard. The single-head `alembic heads` check is a
second step after F-LMG lands.

**Merge.** `git merge --ff-only 69ee7324` — fast-forward (this branch's `cacff77c` was already an ancestor of
main), no conflicts. **Staged SOP-1 1b/1c applied** from `.run/p4/sop1/` with `git apply --3way`: ten files clean;
five conflicts, each resolved keeping both sides — `domain/contracts/compute_job.py`, `domain/journals/summarise.py`,
`domain/reports/framework.py` (main's `controls.release` / `controls.stamping` imports from P5 plus this lane's
`controls.evidence` import), `tests/api/test_me.py` and `tests/pg/test_migrations.py` (head pin `0055` → `0057`,
comment naming the assigned sequence). New files placed: `api/v1/controls.py`,
`tests/domain/platform/test_control_evidence.py`, `tests/api/test_control_evidence_api.py`. `make openapi`
regenerated `docs/api/openapi.json` and `frontend/src/lib/api/schema.d.ts` on main's document.

**Revision file held out of this commit.** `0057_sop_1_control_execution.py` (revision `"0057"`, down_revision
`"0056"`, header rewritten for the assigned sequence and 04 rev 1.21) is final under
`.run/p4/sop1/new/backend/erev_api/db/migrations/versions/`. With `0056` absent from main, Alembic raises
`KeyError: '0056'` and `make lint` fails at its own step "alembic heads must print exactly one head"
(`code_head()` also reports two heads, `0055, 0057`, failing eight `test_release_manifest.py` tests and three doctor
tests); the commit rule requires the lint guard, so the file lands in the second step with the head check. Head pins
already say `0057` (DB-bound, not run).

**Adjustments made while applying.** (1) `record_execution` stamps `engine_release_id` through P5's
`controls.stamping.process_release_id` (D-98 60: the process release, fail-closed outside the dev / test
latest-per-version fallback), replacing the draft's own latest-row lookup — the same rule as the four other
consumers; the unused `Problem` import went with it. (2) `erev_api/privacy/classification.py`: the T-PLT-39 entry
lane P8 had catalogued as `PENDING` (DOC_04) is reconciled to `ACTIVE` now the table is in the code (fifteen columns
unchanged; `test_privacy_classification.py` 12 passed — it failed on the pending entry before). (3) Stale `rev 1.18`
references to the 04 T-PLT-39 row read `rev 1.21` (the merge renumbering).

**SOP-1 state (question 2).** 1a validator: Codex-closed at `232d3a8b`. 1b/1c (table, `record_execution`,
API-R-52 `GET /control-executions` and `GET /releases`, producers CTL-039 / 012 / 001 / 044 / 022 / 029 / 030,
revision 0057) are CPU-validated only: **owed** — every DB-bound test (below) against the Ray-side lane database,
the single-head check, `test_ctl_042_every_producer_records_execution` (full walk), and a Codex review of 1b/1c;
F-CLO's producers (CTL-016 / 019 / 020 / 021 / 024 / 025 / 026) are F-CLO's.

**Governed-document rows carried (question 3): none.** The branch carries no unmerged revision row of 04,
dev-guide, 05 or BUILD_SPEC; the SOP-1 1b/1c slice adds none (04 §18 rule 2 covers a table's own revision and its
deferred FK; the T-PLT-39 section has no pending note to lift).

**Captured statuses (final tree, `cmd; rc=$?`; logs `.run/p4/sop1/gate2-*.log`, `gate-keys.log`).**
`make typecheck` rc=0 (mypy 586 files + tsc). `make lint` rc=0. Engine + architecture + unit (CPU):
rc=1 — 2351 passed, 1 xfailed, 0 failed, 10 errors, every error a setup failure of a database-using unit test
(`FATAL: database "erev_rv_l15_test" does not exist`: `test_cli_idp` ×2, `test_cli_operator`, `test_cli_tenant`,
`test_lists` ×2, `test_time_zones`, `test_uow` ×3) — DB-bound, NOT RUN in effect. Focused doctor / SOP-1 / catalogue /
privacy CPU suite rc=0 — 188 passed. DB-bound modules NOT RUN (lane database not provisioned), collected 15:
`tests/pg/test_doctor.py`, `tests/pg/test_migrations.py`, `tests/domain/platform/test_control_evidence.py`,
`tests/api/test_control_evidence_api.py`, `tests/api/test_me.py`. Release selection `make answer-keys` rc=2 —
254 selected (252 active + 2 withdrawn; the unfiltered corpus), 228 passed, 24 failed, 0 not run; the supervisor's
runs on the same main head select 220 with a filter this lane does not hold, so the two are not the same population.
Every one of the 24 failing ids (`.run/p4/sop1/keys-failed-ids.txt`) is an engine answer key already in the
58-key baseline failing list of the unfiltered corpus, and this slice changes no file under `backend/erev_engine`.

**Not done here.** No merge of main beyond the named head; no database; no ports; no worker / jobs file.

### SOP-1 second step: revision 0057 on 0056 landed (main `4ed5f423`, F-LMG's 0056; 2026-09-20)

Parked from the first step:
- Release selection (220-id population `docs/reviews/loop/sprint/rg-selection.txt`, supervisor's command
  `make answer-keys ID="$(cat …/rg-selection.txt)"`) on `eca4dc4a` (gate context eca4dc4afcd8, tree 2736762e6e23):
  rc=0 — 220 selected; 220 passed, 0 failed, 0 not run, 0 withdrawn (`.run/p4/sop1/gate2-keys-220.log`). The
  earlier unfiltered read (254 selected, 24 failed, all in the 58-key baseline set, engine untouched) stands as such.
- Matrix (docs lane) records SOP-1 owed items as OPEN: DB-bound tests on the Ray-side lane DB; single-head check;
  `test_ctl_042_every_producer_records_execution` full walk; Codex review of 1b/1c.

**Merge.** `git merge --no-ff 4ed5f423` (39 commits since `69ee7324`): one conflict, `backend/tests/pg/test_migrations.py`,
two blocks — the head pin (F-LMG `0056` vs this lane `0057`) resolved to `0057` with a comment naming 0055 (P5),
0056 (F-LMG LMG-1) and 0057 (P4 SOP-1); the function count resolved to F-LMG's measured 76
(`+ tg_migration_batch__transition (0056)`; 0057 adds none). `tests/api/test_me.py` auto-merged and keeps `0057`.
Merge commit `a1ccdd46` (parents `eca4dc4a`, `4ed5f423`) carries the resolution and
`backend/erev_api/db/migrations/versions/0057_sop_1_control_execution.py` (revision `"0057"`, down_revision
`"0056"`, byte-identical to the held copy), committed inside the lint guard. `backend/.venv/bin/alembic -c
backend/alembic.ini heads` prints `0057 (head)` alone.
Merge-commit message defect (not amendable under the lane's git rules): `git commit --no-edit` kept git's
auto-appended `# Conflicts:` lines after the attribution line, so `a1ccdd46`'s message does not END with the
`Co-Authored-By` line; this slice commit does. Noted for the supervisor.

**Captured statuses (final tree `a1ccdd46`; `cmd; rc=$?`; logs `.run/p4/sop1/step2-*.log`).** `make typecheck`
rc=0 (mypy 598 files + tsc). `make lint` rc=0 — its own single-head step passes. Focused doctor / SOP-1 / catalogue
/ privacy suite rc=0 — 188 passed. Release selection (220 ids, supervisor's command) rc=0 — 220 selected; 220
passed, 0 failed, 0 not run, 0 withdrawn (gate context a1ccdd4666ad, tree 1ac9607f9336). Engine + architecture +
unit (CPU) rc=1 — 2381 passed, 1 xfailed, 0 failed, 10 errors, the same ten database-using unit tests failing at
setup on `database "erev_rv_l15_test" does not exist` (DB-bound, NOT RUN in effect). DB-bound SOP-1 modules still NOT
RUN: `tests/pg/test_doctor.py`, `tests/pg/test_migrations.py` (head pin `0057`, function count 76),
`tests/domain/platform/test_control_evidence.py`, `tests/api/test_control_evidence_api.py`, `tests/api/test_me.py`.

**Owed (unchanged; OPEN in the matrix per the supervisor).** DB-bound tests on the Ray-side lane database; the
single-head check against a real database (`test_single_head`); `test_ctl_042_every_producer_records_execution`
full walk; Codex review of SOP-1 1b/1c. Merge order: after F-RPS; F-ADM's 0058 follows this landing.

### P4-CTL029-R1 (Codex packet 1016 on `746ff16c`, verified by the supervisor on main `6be2841a`; D-98 candidate 100)

**Finding.** `domain/reports/framework.py` recorded `record_execution(control_id="CTL-029", population 1,
exceptions 0, PASS)` unconditionally, and only afterwards `_outcome` computed `output_sha256_equal` /
`control_totals_equal` for a rerun and returned SUCCEEDED regardless — a persisted PASS could contradict a returned
mismatch (REQ-RPT-002, 03:536; CTL-029, 03:781).

**Reading (rule (2) check; reported before coding, accepted).** No governed sentence makes a mismatched rerun end
FAILED: REQ-RPT-002 "Re-running with the same snapshot reproduces identical totals and hash" (no status
semantics); the CTL-029 row ("Report run records and reproducibility | Det · Auto | report run register; output
hashes"); 05 §5.6 `REPORT_RUN` (2 attempts, `queueing_lock`, 600 s — retry semantics) and 05 principle 4
(byte-identical outputs); BUILD_SPEC RPS-2 acceptance describes the equal case only; 04 T-RPT-02 is IM-S immutable
after SUCCEEDED (DB-03) and says nothing about reruns; 04 T-PLT-39 / SOP-1 state no CTL-029 recording rule. So the
run and the job stay SUCCEEDED when the rerun produced its output — the mismatch is a control exception — and no
governed document changes (the reserved rows 05 1.18 / 04 1.46 were freed on the merge sheet).

**Ruling applied.** Pure `ctl029_fact(run, original, *, rerun_of) -> Ctl029Fact(result, population_count,
exception_count, detail, flags)` in `framework.py`: first run — PASS 1/0, detail `first_run: true` + the run's hash,
totals and row count (the reproducibility stamp), no flags; rerun of a SUCCEEDED original with output — flags
computed once, PASS 1/0 when both equal, else FAIL 1/1 with `detail` carrying `rerun_of`, both flags, and the
original's AND the rerun's hash / totals (evidence retained, never overwritten); rerun of an original without
output (not SUCCEEDED, or hash / totals null) — NOT_APPLICABLE 0/0, `reason: ORIGINAL_WITHOUT_OUTPUT`, flags False
as the job result always read. The job body loads the original (`_original_of`) and derives the fact BEFORE
`record_execution`; `_outcome(run, params, fact)` takes its flags from that fact on both paths (the job body and the
already-SUCCEEDED early return, which re-derives the fact from the stored rows without recording), so the persisted
fact and the returned flags cannot diverge; the state is always `"SUCCEEDED"`. P5's
`test_ctl_029_run_record_and_rerun` is untouched (`git diff 065e7f65` empty) and collects; the identical case keeps
both flags True.

**Merge.** `git merge --no-ff --no-commit 065e7f65` (122 commits; P5's `4a3120ec` framework edits included): clean,
no conflicts; committed inside the lint guard as `d752482f` with `--cleanup=strip -F` so the attribution line is last.

**Fail-first (on `c9addfa6`, before the code).** `tests/unit/test_ctl029_fact.py` — ImportError "cannot import name
'ORIGINAL_WITHOUT_OUTPUT' from erev_api.domain.reports.framework" (`.run/p4/ctl029/fail-first-unit.log`); the
mismatch cases could not pass on that tree because no fact function existed and the recorded row was
unconditionally PASS.

**Tests.** CPU: `tests/unit/test_ctl029_fact.py` 9 passed after the fix (first run; identical; hash-only,
totals-only and both mismatch; original FAILED / hash null / totals null → NOT_APPLICABLE; purity), each fact also
admitted by `validate_execution`. Database (`tests/domain/reports/test_ctl029_reproducibility.py`, five cases, each
asserting the persisted CTL-029 row — result, counts, detail — AND the returned flags AND run / job SUCCEEDED:
identical, hash-only mismatch, totals-only mismatch, first run, original without output): collected 5, **NOT RUN**
(lane database not provisioned). Mismatch originals are synthetic SUCCEEDED `report_run` copies of a real run with
one stored value altered, because T-RPT-02 is immutable after SUCCEEDED and the inventory report cannot produce a
one-sided difference by itself. Not `pg`-marked: DG-TST-07 (`support/markers.py`) keeps that marker inside
`tests/pg/`; the module is database-bound by fixture like `test_framework.py`. The five carry
`@pytest.mark.control("CTL-029")` (control markers valid: 185 tagged tests).

**Captured statuses (final tree; `cmd; rc=$?`; logs `.run/p4/ctl029/gate*-*.log`).** `make typecheck` rc=0
(mypy 604 files + tsc). `make lint` rc=0 (a first run failed only on a bad test import — `holding` moved to
`support.reference`, `new_id` to `erev_api.db` — before any code was re-measured). Focused CTL-029 / doctor / SOP-1 /
catalogue / privacy rc=0 — 197 passed. Engine + architecture + unit (CPU) rc=1 — 2576 passed, 1 xfailed, 0 failed,
10 errors, the same ten database-using unit tests failing at setup on `database "erev_rv_l15_test" does not exist`
(DB-bound, NOT RUN in effect); `tests/unit/test_controls_report.py` 6 passed. Release selection (220 ids) rc=0 — 220
passed, 0 failed (worktree-dirty development binding on the same code; re-run on the committed head below).
Release selection re-run on the committed correction head `5c0c3401` (immutable gate context 5c0c34010c50, tree
db78ef2eca99; `.run/p4/ctl029/gate3-keys-220.log`): rc=0 — 220 selected; 220 passed, 0 failed, 0 not run,
0 withdrawn. Correction head for Codex's retest: `5c0c3401`.

### Notices while CTL029-R1 was in flight (2026-09-20)

- Supervisor FYI (2026-09-20, integrated batch on 065e7f65): tests/pg/test_doctor.py
  ::test_req_ctl_005_doctor_passes_on_fresh_database and ::test_doctor_detects_failed_verification fail —
  AUDIT_CHAIN_VERIFY's CTL-039 record_execution → controls.stamping.process_release_id → Problem("release-mismatch")
  because the doctor test's job runtime has no stamped process release (the `workspace` fixture only inserts an
  engine_release row); the doctor then reports "0 of 1 tenants; 1 awaiting their first verification" and misses the
  tamper. Owner: P5 as P5-DOCTOR-R1 (stamping / probe-release support, D-98 60 / 94); the CTL-039 producer stays as
  written (population = events checked; FAIL = 1 exception); P4 does not touch test_doctor.py in CTL029-R1.
- P2 heads-up (sprint/l7 354cc322): tests/unit/test_doctor_production_checks.py edited in four places for P2's merged
  Settings rules (EREV_DB_APP_URL in PRODUCTION_ENVIRONMENT; security_hmac_secret_version=1 at both
  settings_override(env="production") sites; KEY_VERSION_PIN joins the expected FAIL set under the existing
  model_fields condition). No doctor code touched; CTL029-R1 (5c0c3401) does not touch that file — no collision.
- P2 confirmed (2026-09-20): the composes test still passes _FakeKeyRing(None), so KEY_VERSION_PIN FAILs by design;
  the module passes 106/106 at P2 354cc322 (.run/p2/merge-main/fixAB-after3.log on l7); no further P2 change to that
  file.

### P4-CTL042-T1: two never-run SOP-1 database tests fixed test-side (batch ci on `065e7f65`; 3,710 passed / 8 failed)

The second integrated batch ran two DB-bound tests no lane had run. (1)
`tests/api/test_control_evidence_api.py::test_req_ctl_002_query_and_export` — ERROR at setup `fixture 'app' not
found`: `tests/api` has no conftest; 45 of its 48 modules define a module-level `app` fixture
(`create_app(app_settings, clock=clock)` over `committed_db`, as `test_account_mappings_api.py`), so the module now
carries that same fixture — the directory's convention, not a new shared fixture. (2)
`tests/domain/platform/test_control_evidence.py::test_ctl_042_verification_producer_records_execution` —
`AttributeError: 'str' object has no attribute 'joinpath'`: `LocalFileStore(root: Path)` received `str(tmp_path)`;
both tests of the module now pass `tmp_path / "files"` (typed `Path`). Producer and API code unchanged — neither test
revealed a code defect. Verification without a database: `pytest --fixtures-per-test` resolves `app`,
`committed_db` and `tmp_path` for every test (no "not found"); the two modules collect 4 tests; both stay DB-bound,
**NOT RUN** by this lane. Still owed as DB proof: `test_ctl_042`'s real walk and `test_req_ctl_002`. The doctor /
audit-verify stamping failures of the same run are P5's (P5-DOCTOR-R1), not this lane's.

Captured statuses (final tree; `cmd; rc=$?`; logs `.run/p4/ctl042/gate-*.log`): `make typecheck` rc=0 (604 files +
tsc); `make lint` rc=0 (control markers valid: 185 tagged tests); focused CTL-029 / doctor / SOP-1 / catalogue /
privacy rc=0 — 197 passed; engine + architecture + unit (CPU) rc=1 — 2576 passed, 1 xfailed, 0 failed, 10 errors =
the same ten database-using unit tests failing at setup on `database "erev_rv_l15_test" does not exist` (DB-bound,
NOT RUN in effect).

### Notices after CTL042-T1 (2026-09-20)

- Merge (supervisor, 2026-09-20 06:02:53): sprint/l15 a7fd97db (P4-CTL029-R1 5c0c3401 + record 1f397412 +
  P4-CTL042-T1 a7fd97db) landed on main as **337e077a** — chain step p4r1, clean merge onto 2dff165b; POSTCHECKS
  typecheck rc0, cpu rc0, selection rc0, aggregate PASS. Merged, not gate-measured: the next integrated batch on the
  wave-3 head measures it, including the two never-run SOP-1 database tests under a gate slot and the five CTL-029
  cases. No further l15 action unless Codex or the batch raises a P4 finding.
- Record hygiene: wrap the 236-char P2 confirmation line (record line ~938) at the next record edit.

### SOP-7 slice 1 — `test_audit_coverage.py` built without a lane database (dispatch D-98 candidate 148 amendment 1; 2026-09-21)

Dispatch: P8 measured SOP-7 (audit coverage; gates P8's SOP-8) and SOP-4 (rate limits and metrics; gates SOP-5) as
NOT MET on main `74899034`; both assigned to this lane, SOP-7 first. Branch fast-forwarded from `a7fd97db` to main
`e6520965` (`git merge --ff-only`, 1,118 commits, 0 ahead). Lane databases: `scripts/check_env.py --names --db`
reports `cannot connect` (OperationalError) for all three `erev_rv_l15_*`, so every DB-bound test of this slice is
written and **NOT RUN** — WAIT for a lane database or a supervisor-directed slot-2 run.

**Incident (disclosed to the supervisor within minutes).** An ad-hoc reachability script of this lane read
`Settings.db_app_url` and called `psycopg.connect` on it; the URL is SQLAlchemy-form, psycopg raised
`ProgrammingError` (not the caught `OperationalError`) and its message echoed the DSN with the `erev_app` password
of `erev_rv_l15_dev` into this lane's tool output (transcript only; nothing written, committed or sent). Rotation of
that credential requested (Ray-side). Corrective: no ad-hoc DSN handling — reachability only through
`scripts/check_env.py --db` (exception type only); lesson stored in the lane practice memory.

**Built.** `backend/tests/domain/platform/test_audit_coverage.py` (three tests, database-bound by fixture, not
`pg`-marked per DG-TST-07; `test_ctl_038_…` tagged `@pytest.mark.control("CTL-038")`):
- `test_ctl_038_every_command_route_writes_audit`: walks the catalogue's command operations (194 on this OpenAPI; the
  six class (a) routes of `SOP_7_EXEMPT` excluded → 188 walked). Each audited operation is exercised by ONE scenario
  of the ordered registry `WALK` (a successful call in a fresh tenant; creations precede the updates and revocations
  that reuse their ids) and must write ≥ 1 `audit_event` with `request_id` = the response `X-Request-Id`, `action`
  matching `^[a-z_]+\.[a-z_]+$` and `actor_kind` USER; a `security_event` route must write a `security_event` with
  that request id (and one of the catalogue's expected kinds when listed); a `query` route (D-98 (20)) must write zero
  `audit_event` rows and change no tenant-table row count except `idempotency_record` (D-98 (49)) and its own
  04 §1.7 personal table. Every walked operation WITHOUT a scenario is named in the failure message (audited and
  query listed separately) — coverage is never hidden. **Scenarios authored: 76 of 188** (the 77th `WALK` entry, `session_login`, is a class (a) exempt route
  exercised for its security evidence; 4 of the 6 `query` operations); **112 uncovered**: 106 `audit_event` routes (contracts, events, estimates, judgements, combinations,
  exceptions, imports, journal runs, migrations, SSP calculator, policies, rule-set rules / tests / publish, POB
  template versions, account-mapping rules / publish, period locks / checklist, files / attachments, saved views,
  support grants, sandboxes / snapshots, `users_reset_mfa`, `roles_propose_change`, …), 4 `security_event` routes
  (`me_mfa_confirm`, `me_regenerate_recovery_codes`, `session_lookup_invitation`, `session_select_tenant`) and the
  2 `query` routes `explain_verify` and `rule_sets_evaluate`. On its first database run the walk will therefore FAIL
  naming them — that is the intended, truthful state until the registry is completed (each scenario needs the route's
  world; several need approvals, jobs or engine worlds).
- `test_req_plt_019_categories_covered`: runs the same walk and asserts every `CATEGORIES` entry has an observed
  action or security kind; missing categories fail by name; a category the catalogue marks pending on a lane
  (AI proposal lifecycle → F-AIX) is reported as pending. With the current scenarios the imports, events, journal
  lifecycle and (until the walk grows) further categories will be named.
- `test_denied_commands_audited`: five routes (`roles_create`, `api_clients_create`, `customers_create`,
  `gl_accounts_create`, `users_invite`) called by a `viewer` → 403 and exactly one `DENIED` `audit_event` per call
  carrying the response's `X-Request-Id` (`auth/dependencies.py::require` already writes it — no source change).

**Known limitation (OPEN).** The no-write boundary is measured by row COUNTS of the tenant-scoped tables; an
UPDATE-only mutation by a `query` route would not move a count. Proposed hardening for the DB iteration: compare
`max(row_version)` / `updated_at` per table or read `pg_stat_xact_user_tables` inside the walk's transaction.

**Statuses (final tree; `cmd; rc=$?`; logs `.run/p4/sop7/gate*-*.log`).** `make typecheck` rc=0 (660 files + tsc).
`make lint`: first run rc=2 at `licence-check` — 17 python packages "no licence metadata" because the lane venv was
stale after the fast-forward; `uv sync --frozen --all-extras` (own project) added the merged lockfile's packages and
the re-run is rc=0 (133 packages, 0 findings; control markers valid: 199 tagged tests). Architecture suite +
`tests/unit/test_audit_catalogue.py` rc=0 — 101 passed. `test_audit_coverage.py` collects 3. No DB-bound test run.

**Next.** SOP-4 (rate limits and metrics) as the next slice; SOP-7 scenario completion and the first walk run need a
lane database (WAIT) — the run will name the uncovered operations exactly.

### SOP-4 slice — rate limits and metrics (dispatch D-98 candidate 148 amendment 1; 2026-09-21)

**Reused, not rebuilt.** `auth/ratelimit.py` already held the SAR-13 policy (`request_limits`, `RequestRateLimiter`,
`TOKEN_PER_CLIENT_ID` 30, `BROWSER_PER_SESSION` 1,200, `API_CLIENT_DEFAULT_PER_MINUTE` 600, `OPENAPI_RATE_LIMIT_LINE`)
but nothing called it; `controls/metrics.py` held the MET-01 to MET-11 definitions and the label-safety predicate
but no route existed; `Settings` already carried `metrics_enabled` / `metrics_token`. Minimal source added:
- `auth/api_clients.py`: `TokenPrincipal.rate_limit_per_minute` selected with the bearer token's client.
- `auth/dependencies.py`: `admit_request(request, route_class, now=…, …)` — one `RequestRateLimiter` per api
  process on `app.state.request_rate_limiter` (DG-API-07); refused → 429 `rate-limited`, detail "Too many requests.
  Try again in N seconds.", `Retry-After`; called in `_bearer_context` (API_CLIENT bucket at the client's limit,
  default 600) and at the top of `_session_context` (BROWSER_SESSION bucket per session id, operators included).
  Raised from the dependency, before any handler, so never stored as an idempotent response (DG-KRN-IDEM-03,
  `UNSTORED_STATUSES` already lists 429).
- `api/v1/oauth.py`: the TOKEN bucket (30 per minute per client id) admitted before `issue_token`.
- `main.py`: `description=OPENAPI_RATE_LIMIT_LINE` on the FastAPI app (published in `info.description`),
  `app.state.request_rate_limiter`, and `GET /metrics` added at the application root with
  `include_in_schema=False` (04 API-R-53: outside `/api/v1`, never in the OpenAPI document).
- `api/deps.py`: `/metrics` on `PUBLIC_PATHS` for the DG-ARC-04 guard rule — its guard is the
  `EREV_METRICS_TOKEN` bearer inside the handler.
- `api/metrics.py` (new): `MetricsRegistry` (counters, histograms with the MET-02 buckets, gauges; every sample
  passes `controls.metrics.validate_labels`), Prometheus text format 0.0.4 renderer emitting `# HELP` / `# TYPE`
  for all eleven definitions, `observe_http` (MET-01 by route template / method / status class; MET-02 duration),
  the api pool gauge (MET-11, `component="api"`, from `app_engine().pool.checkedout()`), and `metrics_endpoint`:
  404 `not-found` while `EREV_METRICS_ENABLED` is false, 401 `unauthenticated` without the exact bearer
  (`secrets.compare_digest`), else the exposition; no tenant context.
- `api/middleware.py`: the lifecycle middleware observes MET-01 / MET-02 for every request (route template, never
  the concrete path).
- `docs/guides/runbook.md`: new section "Rate limits and metrics" — the bucket table, the 429 shape, the
  DG-API-07 per-instance note, the metrics settings, a scrape example and the label policy. The runbook carries no
  revision rows, so no number was requested.
- `docs/api/openapi.json` regenerated by `make openapi` (`info.description` only; no path change).

**OPEN (recorded, not hidden).** The worker-side series MET-03 to MET-10 are exposed with `# HELP` / `# TYPE` and the
samples the api process observes — none: the scrape-time database read of BUILD_SPEC BS1-D-36 needs a platform-wide
read path (a `platform_session` records a `PLATFORM_SCOPE_USED` security event per use, unsuitable for a 15-second
scrape), so it is a follow-up needing a design ruling; the acceptance tests require the names, which are present.

**Tests.** `tests/api/test_metrics.py` (3, build the app WITHOUT a database): disabled → 404 `not-found`; missing /
wrong bearer → 401; correct bearer → 200 `text/plain; version=0.0.4` holding all eleven names, a MET-01 sample for
`/api/v1/healthz`, MET-02 buckets, the pool gauge, and no label value shaped like a uuid or an amount (the histogram
bound `le` is a bucket boundary, excluded from the amount check); `/api/v1/metrics` → 404 and the committed OpenAPI
has neither `/metrics` nor `/api/v1/metrics`. `tests/api/test_rate_limits.py`: `test_openapi_publishes_limit`
(CPU; fail-first captured before `make openapi`: `'600 requests per minute per API client' in ''` failed,
`.run/p4/sop4/fail-first-openapi.log`); `test_req_plt_037_api_client_limit` (client at 5 per minute: 5 × 200, the
sixth 429 with `Retry-After`, a limited command's 429 not replayed under the same `Idempotency-Key` after the
window, 200 again after `clock.advance(60 s)`) and `test_token_endpoint_limit` (30 × 200 then 429; 200 after the
window) — DB-bound, collected, **NOT RUN** (no lane database). Fail-first for the metrics tests could not be captured:
code and tests were written together and the lane's git rules forbid switching trees.

**Statuses (final tree; `cmd; rc=$?`; logs `.run/p4/sop4/`).** New CPU tests rc=0 — 4 passed (after excluding
`le` from the amount check; the first run failed on that test defect only). `make typecheck` rc=0 (661 files + tsc).
`make lint` rc=0 (control markers valid: 199). Architecture suite + related unit tests (`-k middleware or route or
openapi or ratelimit or metrics or deps or guides or catalogue`) rc=0 — 62 passed. Six SOP-4 tests collect.


### Design note (docs first, for a later ruling): MET-03 to MET-10 worker-side samples (SOP-4 OPEN)

Ruled engineering (supervisor, 2026-09-21): not built this round; the names stay exposed without samples; no
`platform_session` read at scrape time (one `PLATFORM_SCOPE_USED` security event per scrape is unsuitable and the
event is not to be suppressed); no guard weakening. Question for the ruling — which of three shapes gives the
worker-side series (`erev_jobs_total`, `erev_job_duration_seconds`, `erev_job_queue_depth`,
`erev_computation_duration_seconds`, `erev_close_step_duration_seconds`, `erev_outbox_messages`,
`erev_export_failures_total`, `erev_audit_chain_verification_failures_total`) their samples:
1. **BS1-D-36 scrape-time read** as written — the api process reads `job`, `outbox_message`,
   `audit_chain_verification`, `contract_computation` and the close-step tables across tenants at each scrape.
   Needs a platform-wide read path that is not `platform_session` (RLS blocks `erev_app` without a tenant; the
   owner role is not held by the api process) — a dedicated `metrics` scope with a bounded read-only policy and
   no per-use security event would be a new DG-KRN-DB rule.
2. **Worker-exposed in-process counters** — the worker process keeps its own registry (the same
   `MetricsRegistry`) fed by the job runtime (`run_job` outcomes and durations, outbox relay, chain verification)
   and serves its own `GET /metrics` (or pushes to the api process); BS1-D-36 "api process only" would need
   amending, and queue depth / outbox backlog are database facts, not process facts.
3. **Bounded periodic snapshot** — a SCHEDULED job (worker, system principal per tenant, every 30 s per MET-05's
   note) writes the platform-wide figures to one small table (or the api process's registry over the job's
   result); the api serves the last snapshot with a `scraped_at` staleness gauge. Keeps "api process only", uses
   existing job plumbing, costs one row per interval.
Lane P4's preference: 3 (no new database scope, no per-scrape security event, staleness visible), with 2 for
duration histograms the worker alone observes. Decision owner: supervisor (D-98 candidate); not built here.

### SOP-7 slice 2 — the scenario registry grows to 113 of 188; the walk stays EXPECTED RED (2026-09-21)

Precondition applied first: main `5db2d3ba` merged into `sprint/l15` (`git merge --no-ff --no-commit`, clean, no
conflicts) and committed as `f5f1af57` only under the one condition `make lint && tests/architecture` on the merged
tree — lint rc=0, architecture **95 passed**.

Registry: `WALK` now holds 113 entries = **112 authored scenarios of the 188 required** plus the exempt
`session_login` exercised for its LOGIN_SUCCEEDED evidence (was 77 entries / 76 authored). Added: access-review
confirm-revocation and complete (two reviewers so every item can be decided), file upload (SSP study) with
attachment create / void on an SSP book version, SSP version submit / withdraw and entry delete, FX version submit /
withdraw, config test case create / update / delete, a DATA_QUALITY rule set with rule upsert / delete, test case,
lint, test and submit, POB template version create / update / test / submit, saved view create / update / delete,
SoD exception revoke (after its approval), role change proposal, principal-agent change proposal and bundle
components, support grant create / revoke (operator from `support.operators`), tenant snapshot (job run) and sandbox
requests by a controller, period lock request on a second period, and MFA reset of an enrolled admin (placed after
her approvals). `periods_cancel_close` now sends the required `reason_code`. The module collects 3 and is lint-clean.

**Uncovered — 76 operations, named by the walk's failure message on its first database run** (EXPECTED RED, no
`xfail`, per the CTR-17b precedent, until the registry is complete): 70 `audit_event` routes —
`account_mapping_rules_create`, `account_mapping_rules_delete`, `account_mappings_publish`, `approvals_bulk_approve`, `combination_groups_create`, `combination_groups_submit`, `combination_suggestions_dismiss`, `contract_estimates_create`, `contract_events_append`, `contract_events_preview`, `contracts_apply_hold`, `contracts_create`, `contracts_distinct_review`, `contracts_release_hold`, `contracts_replace_draft`, `contracts_request_void`, `contracts_submit_activation`, `contracts_update_memos`, `estimate_versions_create`, `estimate_versions_preview`, `estimate_versions_submit`, `estimate_versions_update`, `estimate_versions_withdraw`, `event_submissions_withdraw`, `events_request_void`, `exceptions_assign`, `exceptions_dismiss`, `exceptions_reprocess`, `exceptions_request_waiver`, `exceptions_resolve`, `import_mapping_profiles_create`, `import_mapping_profiles_publish`, `import_mapping_profiles_submit`, `import_mapping_profiles_test`, `import_mapping_profiles_update`, `imports_cancel`, `imports_create`, `imports_submit`, `journal_runs_cancel`, `journal_runs_create`, `journal_runs_export`, `journal_runs_submit`, `judgements_create`, `judgements_submit`, `judgements_update`, `migrations_cancel`, `migrations_create`, `migrations_import`, `migrations_profile`, `migrations_reconcile`, `obligations_request_ssp_override`, `periods_checklist_sign`, `periods_checklist_waive`, `periods_request_permanent_lock`, `periods_request_reopen`, `pob_template_versions_publish`, `policies_create`, `policies_presets_legacy_parity`, `policies_publish`, `policies_submit`, `policies_test`, `policies_update`, `policies_withdraw`, `policy_overrides_create`, `policy_overrides_submit`, `rule_set_versions_publish`, `session_accept_invitation`, `ssp_calculator_exclusions_create`, `ssp_calculator_runs_create`, `ssp_calculator_runs_create_draft_version`; 2 `query` routes — `explain_verify`, `rule_sets_evaluate`; 4 `security_event`
routes — `me_mfa_confirm`, `me_regenerate_recovery_codes`, `session_lookup_invitation`, `session_select_tenant`.
These need engine / import / journal / migration / close worlds (contracts, events, estimates, judgements,
combinations, exceptions, imports and mapping profiles, journal runs, migrations, SSP calculator, policies and
overrides, period reopen / permanent lock / checklist items, publish steps behind approvals) or a TOTP code
(`me_mfa_confirm`, recovery codes), a multi-tenant user (`session_select_tenant`) or an invitation token
(`session_lookup_invitation`, `session_accept_invitation`). The written scenarios are blind (no lane database);
their first database run will also name any body that a route refuses.

**Statuses (final tree; `cmd; rc=$?`; logs `.run/p4/sop7/gate*-*.log`, `gate-cpu-full.log`).** Full CPU set
(engine + unit + architecture) rc=1 — **3630 passed, 1 xfailed, 0 failed, 10 errors**, every error a setup failure
of a database-using unit test on `database "erev_rv_l15_test" does not exist` (`test_cli_idp` ×2,
`test_cli_operator`, `test_cli_tenant`, `test_lists` ×2, `test_time_zones`, `test_uow` ×3) — DB-bound, NOT RUN in
effect. `make lint` rc=0 (control markers valid: 199 tagged tests). `make typecheck` rc=0 (673 files + tsc). The
three SOP-7 tests remain NOT RUN (lane databases unreachable).

### Codex production-20260921-2306 §4–§5 on SOP-7 `16e9c8bc`: R1 category false-green, C1 counts (fixed in slice 2)

- **R1.** The category test put an unobserved category that the catalogue marks pending on a lane into a
  `pending` list and asserted only on `missing`, so the mandatory AI proposal-lifecycle category (pending on
  F-AIX, no action literal) could pass silently. Fix: `support.audit_catalogue.uncovered_categories(actions,
  kinds)` names EVERY unobserved category — a pending one with its owner ("AI proposal lifecycle (pending on lane
  F-AIX)") — and the DB test asserts that list is empty; no skip, xfail or partial-green path. CPU proof:
  `tests/unit/test_audit_catalogue.py::test_req_plt_019_pending_category_still_fails_by_name` — an
  otherwise-complete observation (one action or kind of every evidenced category) still fails naming the AI
  lifecycle; nothing observed names all 14; once the lane's action lands and is observed the category passes like
  any other.
- **C1.** Counts corrected above: 194 − 6 = 188 required; `session_login` is class (a) exempt, so the registry's
  entries minus it are the authored scenarios — slice 1: 77 entries = 76 authored, 112 uncovered (106 audit + 4
  security + 2 query); slice 2: 113 entries = 112 authored, 76 uncovered (70 + 4 + 2). `required_operations()` and
  `test_sop_7_required_operations_exclude_class_a` pin the 188 and the exclusion. The walk computes the
  uncovered set from the registry alone (`uncovered_operations()`) and reports it in the same assertion as the
  scenario failures. Codex 2338 wording correction: an UNCAUGHT scenario assertion (e.g. `books_update`'s GET
  precondition) could abort the walk before that assertion; `_exercise` now records a raising scenario as the
  named failure "<operation>: the scenario raised <ExceptionType>" and continues, so one run does report the
  full set — the earlier "whatever else fails" wording described the intent, not the code.
- Still open, unchanged: the row-count-only no-write limitation; every SOP-7 DB test NOT RUN.

- **R1 fail-first captured against the pre-fix code** (`.run/p4/sop7/fail-first-r1-category.log`, logic quoted
  from `7031f778` via `git show`): with the otherwise-complete observation (one action or kind of every evidenced
  category) the old test put "AI proposal lifecycle (pending on lane F-AIX)" in its unasserted `pending` list and
  its assertion `not missing` **passed silently**; `uncovered_categories` at `e739a7f5` returns exactly that name
  and the assertion fails by name. C1 arithmetic re-checked from the registry: 188 required; 76 uncovered =
  70 `audit_event` + 2 `query` + 4 `security_event`.

### Codex production-20260921-2334 §1–§4 on SOP-4 `d93ec3b9`: P4-SOP4-BROWSER-1 and C1 (fixed; UNFREEZE slice)

**BROWSER-1.** Browser admission lived only in `_session_context`, so `authenticate_session` alone (GET /session),
`get_optional_request_context` with no active workspace (a multi-membership user's `GET /me`),
`require_authenticated(tenant=False)` and `require_operator` never entered the 1,200-per-minute session bucket.
Fix: `_admit_browser_session(request, auth)` is called inside `authenticate_session` — the one common
authentication point of every cookie path — keyed on the real session identity (`auth.session.id`) and counted
once per request through a `request.state` marker, however many session dependencies a route resolves; the admit
in `_session_context` is removed (no double counting); login and MFA challenges keep their own address / email
limiters. `GET /session` (`api/v1/session.py::session_get`) narrows its catch: an invalid cookie is still an
anonymous session, a `rate-limited` Problem is re-raised, never degraded to an anonymous 200.
Witnesses — CPU, app built without a database, `sessions.authenticate` faked with the request's REAL clock-driven
facts (`tests/unit/test_rate_limit_wiring.py`, 4): the 1,200 / 1,201 boundary with 429 `rate-limited` +
`Retry-After` and the 60-second reset; no-workspace, tenant-free and operator dependencies all admitted and counted
ONCE for one request (three dependencies on one request consume one admission; the next request is refused on
every path); `session_get` raises the 429; another session is a separate bucket. **Fail-first captured against
`12db5741`** (`.run/p4/sop4b/fail-first-wiring.log`): boundary and once-per-request witnesses "DID NOT RAISE
Problem", the `session_get` witness reached the anonymous path. DB-bound witness (written, NOT RUN):
`tests/api/test_rate_limits.py::test_browser_session_limit_on_every_authenticated_path` — active workspace
(`GET /roles` ×1,200 then 429 + `Retry-After`, `GET /session` shares the refusal, reset after 60 s), no workspace
(a user given a second membership so sign-in opens none; `GET /me` ×1,200 then 429), and a fresh session of the
same user as its own bucket.

**C1.** The idempotency retry accepted any non-429 status. Now the deliberately invalid `POST /contracts`
(`external_id` only) asserts its own named outcome — 422 `validation-failed` naming the required booking fields
(`contracting_entity_code`, `transaction_currency`, `inception_date`, `lines`) — with no `Idempotent-Replay`
on that first execution, and a third call under the same key replays the 422 with `Idempotent-Replay: true`
(422 is stored; the earlier 429 never entered the store). Window, limit and same-key assertions kept.

**Statuses (final tree; `cmd; rc=$?`; logs `.run/p4/sop4b/`).** CPU: wiring witnesses 4 + metrics 3 + OpenAPI 1 =
8 passed. `make typecheck` rc=0 (673 files + tsc). `make lint`: one run rc=2 at `secrets-check` on the witness's
literal `token="…"` kwarg (a synthetic probe value, flagged as PASSWORD_ASSIGNMENT) — rewritten as a non-literal
expression, re-run rc=0 (secrets 0 findings; control markers valid: 199). Architecture 95 passed. Full CPU set
(engine + unit + architecture) on the final CODE with the earlier witness revision: rc=1 — 3636 passed, 1 xfailed,
0 failed, 10 lane-DB setup errors (NOT RUN in effect); the witness module's later test-only edits pass on their own
(4). MET-03..10 stays the disclosed gap. Main not merged (per instruction: after p6f1 lands).

### Codex production-20260921-2359 §4–§6: BROWSER-1 CLOSED at source (`93da29aa`); C1 corrected again

Codex closed BROWSER-1 at `93da29aa` (second reviewer corroborating; the public DB witness stays NOT RUN, no HTTP
operator case). C1 was still open: the retry body (`external_id` only) failed SCHEMA validation before
`contracts_create` / `run_command` — `problems.py` builds that 422 without settlement and `UNSTORED_STATUSES`
applies only through `_settle_failed_command`, whose sole production caller is `run_command`'s handler-exception
catch — so the "stored 422 replay" assertion had no completion path (an IN_PROGRESS key was a possible consequence).
Fix: the retry is now a SCHEMA-VALID `POST /customers` by the API client (scopes `contract.read`,
`masterdata.maintain`; approval scopes are refused by CTL-037, masterdata is not) that reaches `run_command`
and succeeds exactly — 429 with no `Idempotent-Replay` while limited; after the window an exact 201 whose body
echoes the code and name, no replay header; a third call under the same key and body returns 201 with
`Idempotent-Replay: true` and a JSON body identical to the first — proving the 201 was stored and the 429 never
was. Window, limit and same-key assertions kept; no arbitrary non-429 check anywhere. DB-bound, NOT RUN.
The `68606a6b` aggregation change is under Codex's separate review.

### Merge of main `0959b560` (p4s2 STOP: audit-catalogue pin conflict with F-CTR's CTR-17; 2026-09-21)

The queued line stopped before merging ("17:44:07 STOP p4s2: unexpected conflict set:
backend/tests/unit/test_audit_catalogue.py"): F-CTR's CTR-17 landed as `0959b560` with 7 new command operations
(`contract_modifications_create`, `contracts_regroup`, `modifications_classify`, `modifications_preview`,
`modifications_submit`, `modifications_update`, `modifications_withdraw`), raising the catalogue's operation pin
to 201 and the unverified bound to 32 (`+ modifications_preview`), while this lane's R1 / C1 tests sat on the same
lines. Resolution as the UNION: main's `<= 32` bound with its CTR-17 comment, then this lane's two tests; the
operation pin 201 is main's and is the true combined count (`command_operations()` 201 = `ROUTES` 201, no missing
or extra ids); the required-set pin becomes `201 − 6 = 195` (194 at the P4 slice + 7 CTR-17 operations), stated in
the test's docstring. `make openapi` re-run on the merged tree: no stale diff (`info.description` present; 300
paths). Consequence for SOP-7: required 195, authored 112, **uncovered 83 = 77 audit + 4 security + 2 query** —
the 7 CTR-17 operations join the named uncovered list (the walk reports them by name). Committed under the one
condition `make lint && merge_buildspec --check && tests/architecture + tests/unit/test_audit_catalogue.py +
tests/unit/test_guides.py`; counts in the merge report.

### LANDED: SOP-4 + SOP-7 partial (sprint/l15@0ed9c00f → main 0bf5acea; 2026-09-21)

Quoted from the supervisor: "18:10:47 p4s3 PASS: merged p4s3 sprint/l15@0ed9c00f onto 4bd5a67f: 0bf5acea |
POSTCHECKS: typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS"; selection 220 / 220; clean merge. On main:
`test_ctl_038_every_command_route_writes_audit` and `test_req_plt_019_categories_covered` EXPECTED RED as
recorded (195 required / 112 authored / 83 uncovered, one aggregate assertion, no xfail); every DB test NOT RUN —
batch #8 measures them. OPEN unchanged: the MET-03..MET-10 design note, the row-count-only no-write limitation.
Branch fast-forwarded to `0bf5acea` (green) before this record-only commit; next slice: the remaining 83 SOP-7
operations, engine and import worlds first.

### SOP-7 slice 3 — engine, import, journal, migration, policy and session scenarios (2026-09-21)

Precondition: branch fast-forwarded to the green main `0bf5acea` (LANDED head) before this slice; the landing
record is `6ef6a1d2`. Registry: `WALK` now holds 175 entries = **174 authored of the 195 required** plus the exempt
`session_login` (was 113 / 112). Third tranche, engine and import worlds first as ruled:
- **Engine (PRD K-02 world, its own tenant).** `_engine(w)` builds `k02_world` lazily (maya = `place.author`,
  priya, marcus; AVM-US, AVM-SEAT-MO, US-LIST, AVM-MAP-2026-01), books, activates and computes a K-02 contract via the
  factories, and points the walk's evidence reader at that tenant (`World.evidence_tenant_id`, reset per scenario).
  HTTP scenarios there: contracts create / replace-draft / submit-activation / update-memos / apply-hold /
  release-hold / request-void (a second draft) / distinct-review; `contract_events_append` and `_preview`
  (`DELIVERY_RECORDED` on O1, `If-Match` from the contract ETag); `obligations_request_ssp_override` (obligation
  id from the tenant rows); estimates (create, version create / update / preview / submit / withdraw);
  judgements (create / update / submit); combination groups (create / submit); `events_request_void` and
  `event_submissions_withdraw`; the CTR-17 modifications (create with the K-02 upgrade body, classify, update,
  preview, submit, withdraw); policy overrides (create / submit); journal runs (create / cancel); SSP calculator
  (run create with the job run, exclusion, draft version).
- **Walk tenant.** Imports: a valid `legacy_sku_ssp` workbook (`SKU_SSP_FIXTURE`) uploaded as `IMPORT_SOURCE`,
  `imports_create` (job run), `imports_submit`, `imports_cancel` (a second import); import mapping profiles
  (create / update / test / submit); migrations (create from a `LEGACY_DATABASE` upload, cancel); policies
  (create `billing.posting = ERP` at TENANT scope, update, test, submit, withdraw, `presets/legacy-parity`);
  `rule_sets_evaluate` (query class: the DATA_QUALITY draft's `version_id`); the two checklist templates are now
  created before the close so `periods_checklist_sign` / `_waive` have items; P02's lock is approved by the
  controller, then `periods_request_permanent_lock` and `periods_request_reopen`; `session_select_tenant` (a second
  membership so sign-in opens none); `session_lookup_invitation` provoked to FAIL on purpose — the route's evidence is
  written on refusal (D-98 (20)), so `REFUSAL_EVIDENCE` lets a 404 / 422 count as the exercised outcome and the
  `security_event` assertion still applies; `session_accept_invitation` with the token read from the invitation's
  outbox message; `me_mfa_confirm` (TOTP via `erev_api.auth.totp` at the frozen clock; the rotated cookie is kept)
  and `me_regenerate_recovery_codes`.
- **Uncovered — 21 operations, named by the walk** (20 `audit_event` + 1 `query`): `account_mapping_rules_create`,
  `account_mapping_rules_delete`, `account_mappings_publish`, `approvals_bulk_approve`,
  `combination_suggestions_dismiss`, `contracts_regroup`, `exceptions_assign`, `exceptions_dismiss`,
  `exceptions_reprocess`, `exceptions_request_waiver`, `exceptions_resolve`, `import_mapping_profiles_publish`,
  `journal_runs_export`, `journal_runs_submit`, `migrations_import`, `migrations_profile`, `migrations_reconcile`,
  `pob_template_versions_publish`, `policies_publish`, `rule_set_versions_publish`, `explain_verify`. They need
  exception items (raised by failed jobs), the publish steps behind approvals, a real legacy database for the
  migration steps, computed journals for submit / export, a combination suggestion, a regroup source with two
  obligations, and the explain measure vocabulary. All 174 scenarios remain blind (no lane database); the first
  database run names every refused body. `test_ctl_038` and `test_req_plt_019` stay EXPECTED RED (no xfail).

**Statuses (final tree; `cmd; rc=$?`; logs `.run/p4/sop7/gate3-*.log`).** `make lint` rc=0 (control markers
valid: 200 tagged tests). `make typecheck` rc=0 (685 files + tsc). Architecture + `test_audit_catalogue.py` +
`test_guides.py` rc=0 — 113 passed. The coverage module collects 3.
Full CPU set (engine + unit + architecture, background run, `gate3-cpu-full.log`) rc=1 — **3778 passed, 1 xfailed,
1 failed, 10 errors**: the ten errors are the lane-DB setup failures as before (NOT RUN in effect); the one failure is
`tests/unit/deploy/test_backup_restore_scripts.py::test_diagnostics_never_echo_a_dsn_or_secret` — "FAIL backup:
erev-20260922T013140Z.digests.json already exists": P6's `scripts/backup.sh` names a backup by the UTC second and the
test's two backups in one second collide; nothing of this slice touches deploy scripts or that test (re-run alone,
twice: 1 passed in 7.07s;1 failed in 1.25s;). Reported to the supervisor as P6's timing flake, not a P4 regression.

**Count change on main (supervisor heads-up, 2026-09-21).** P8's landing `143062c8` added two REQUIRED command
operations, `users_anonymise` and `files_shred` (SOP-5; 05 PRV-07): on current main ROUTES = 203, exempt 6,
**required = 197** (the landed pin at `test_audit_catalogue.py` still says 195; P8 fixes it forward). This tree is on
`0bf5acea` and measures 195 / 174 authored / 21 uncovered; after the merge of the green head the supervisor names,
the counts are re-derived from the merged catalogue — 174 of 197 authored and 23 uncovered including the two privacy
commands unless scenarios are authored for them in the same step (not exempted).

### Pre-READY slice — merge of main `896e9b16`, Codex 0223 INVITATION-1 / MODIFICATION-1, the two privacy walks (2026-09-21)

**Merge.** The supervisor named `896e9b16` (P8's fix-forward P8-MERGE-SOP7-PIN-1, chain step PASS 19:42:53) as the GREEN
head; merged into sprint/l15 as `962b43a0` without rebasing (52 commits in, 2 of mine ahead; 64 files, no conflict, no
P4-owned file touched; `uv.lock` unchanged, no re-sync needed). The merged catalogue pin reads 203 / ≤32 / 203 − 6 = 197
(P8's fix-forward; untouched here). **Lineage of the required count: 195 (main `0bf5acea`, ROUTES 201) → 197 (P8 `143062c8`
added `users_anonymise` + `files_shred`; pin re-derived by P8 in `896e9b16`).** F-ADM DIN-12 (+5 integration commands →
202) is not on this head; walks for those are authored only once they exist on a merged tree.

**Codex production-20260922-0223 §1–§2 (both accepted as authored positive-fixture defects; test-only fixes, applied after
the merge as ruled).**
- *P4-SOP7-TRANCHE3-INVITATION-1.* The walk resent (token rotated) and then removed (token nulled) its `membership`, yet
  `s_session_accept_invitation` accepted that same membership with an unordered first outbox payload — on the intended path
  `memberships.accept_invitation` (INVITED + digest match + unexpired) could only 404. Fixed: `_fresh_invitation()` invites a
  fresh membership inside the acceptance scenario (201 asserted), reads the ONE outbox message of that aggregate with
  `.scalar_one()` (no ordering guess) and asserts `sha256_hex(token)` equals the row's stored `invitation_token_sha256`
  before accepting; after the 2xx `_membership_status()` asserts the row is `ACTIVE`. `session_accept_invitation` stays OUT
  of `REFUSAL_EVIDENCE` (a 404 / 422 is a named failure); the resend / removal and the deliberate lookup refusal stay.
- *P4-SOP7-TRANCHE3-MODIFICATION-1.* The WALK ran create → classify → update → preview → submit → withdraw, but
  `update_modification` resets `proposed_treatments` and both preview pointers and `request_preview` only defers the
  `CONTRACT_COMPUTE` job, so `submit` refused UNCLASSIFIED / no stored preview. Fixed: WALK reordered to create → update →
  classify → preview → submit → withdraw; `s_modifications_preview` runs the 202's job through the existing tenant-correct
  seam `_run_job_in(w, e.place.tenant_id, job_id)` (the K-02 modification tests' FETCHED-marker + `registry.run_job` path),
  asserts `GET /jobs/{id}.state == "SUCCEEDED"` and a persisted `impact_preview` with its `sha256` on the row, then submit,
  then withdraw.

**The two privacy walks (not exempted).** `s_users_anonymise` erases a fresh colleague of the tenant as Tomas with `REASON`
(≥ 10 chars); the step-up check (≤ 5 min) holds because the walk's frozen clock never moves (a second TOTP code at the same
step would be a T-PLT-04 replay, so Tomas is not stepped up again). `s_files_shred` uploads a fresh `ATTACHMENT`-purpose file
as Tomas (`settings.manage`) and shreds it — its own file, so the walk's SSP study stays readable. Both are DB-bound and
NOT RUN here (lane DB absent); expected evidence `app_user.anonymise` + `tenant_membership.remove`, `file_object.shred`.

**Counts derived from the merged tree (`.run/p4/sop7/counts-merged.txt`):** ROUTES 203, exempt 6, **required 197,
authored 176, WALK 177 entries (no duplicate ids), uncovered 21 = 20 audit + 1 query** — the same 21 named before:
account_mapping_rules_create / _delete, account_mappings_publish, approvals_bulk_approve, combination_suggestions_dismiss,
contracts_regroup, exceptions_assign / _dismiss / _reprocess / _request_waiver / _resolve, import_mapping_profiles_publish,
journal_runs_export / _submit, migrations_import / _profile / _reconcile, pob_template_versions_publish, policies_publish,
rule_set_versions_publish; explain_verify (query). Still EXPECTED RED, no xfail.

**Gates on the merged tree:** `make lint` rc=0 (200 tagged); `make typecheck` rc=0 (687 files); architecture + catalogue +
guides 117 passed. Full CPU set: see the line below.
Full CPU set on the merged tree (`.run/p4/sop7/preready-cpu-full.log`, started 19:48:07, ended 19:59:24): **"3880 passed,
1 xfailed, 10 errors in 675.09s (0:11:15)"**, ZERO `FAILED` lines; the ten errors are exactly the known lane-DB fixture
set (test_cli_idp 2 / test_cli_operator 1 / test_cli_tenant 1 / test_lists 2 / test_time_zones 1 / test_uow 3). The P6
backup digests flake did not occur in this run. Reporting defect (P4): the run's END was read by the supervisor 24 minutes
before I reported it — the background notification arrived late and I did not read the gate log at the start of the turn;
corrected practice: read `.run/p4/**/*.log` first thing every turn. Commit condition (`.run/p4/sop7/preready-commit.sh`):
`make lint` rc=0, the captured summary re-parsed (0 failed, the known ten by file), tree identity = exactly the two files,
and the walk module's mtime (19:46:28) before the run began; the record was appended during the run (docs only, read by no
test), stated here rather than hidden. The CPU set is not re-run.

### Codex production-20260922-0339 §5 — INHERITED world-builder defect at `a3f64336`: TOTP replay in `_world` (fixed; 2026-09-21)

**Finding (root-confirmed by the supervisor; inherited from the earlier tranches, not the 0223 corrections).** `_world`
called `step_up(app, clock, enrolled(app, clock, tomas_member))` at an UNCHANGED `FrozenClock`. `principals.enrolled`
confirms the current TOTP code through `POST /me/mfa/confirm`, which stores `last_used_step` on the factor (T-PLT-04) and
reissues the session with `mfa_verified_at = now`; `step_up` then re-sent the SAME code to `POST /session/mfa`, whose
`totp.matching_step(..., last_used_step=…)` refuses the replay — so the world build failed before any walk ran. The 176 of
197 authored count is a static registry count and never established runtime acceptance.

**Why a step-up is still needed after `enrolled` — WITHDRAWN (Codex production-20260922-0349 §4; see the landing entry
below).** ~~`enrolled` ends with the tenant selection (`workspace(...)`), and the membership reissue in
`domain/platform/memberships.py` sets `mfa_verified_at=None` — the enrolment verification does not survive the tenant
switch, so the verified-at-enrolment session alone would not pass `mfa.step_up_fresh_at` for `users_anonymise`.~~ This
claim was unsupported: `auth.sessions.select_tenant` PRESERVES `mfa_verified_at`; `memberships.py:78–88` is the invitation
principal. The fix nevertheless keeps a real step-up (valid, not the only valid fix): **the clock advances one TOTP step (`totp.STEP`, 30 s) between
`enrolled` and `step_up`** (P8's `fresh_step_up` pattern in `test_privacy_commands.py`), so the step-up code is at a fresh
step and the replay / freshness controls are untouched. Every scenario then runs at that instant under the frozen clock, so
Tomas's step-up stays inside the five-minute window without a second code; the `s_users_anonymise` docstring now says so
("one TOTP step after his enrolment") instead of "the frozen clock never moves". `s_files_shred` needs no step-up.

**Change.** Test-only, in `test_audit_coverage.py` (`_world` + the anonymise docstring); no source, catalogue or count change
(203 / 6 / 197 / 176 / 21). DB-bound, NOT RUN here (lane DB absent; a future integrated head containing the slice measures it — Codex 0620 §3 correction). Commit under the supervisor's
speed condition for a test-only change in a DB-bound module: `make lint` + `make typecheck` + tests/architecture + the
catalogue + collect-only of the module + a diff-stat of exactly this file and the record; no full CPU re-run
(`a3f64336`'s run covers the rest).

### LANDED: SOP-7 slice 3 + Codex 0223 / 0339 fixes (sprint/l15@e7991b5b → main e01062d2; 2026-09-21)

Supervisor's line, quoted: "21:15:21 p4s5 PASS: merged p4s5 sprint/l15@e7991b5b onto b68a4b08: e01062d2 | POSTCHECKS:
typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS"; "engine+architecture+unit: 3909 passed, 1 xfailed in 577.52s (0:09:37)";
answer-key selection 220 / 220; report sha256 `016a4cfaa006801e58476bc866be7d733a79964693041ffa2ed54a04e1463cb4`, run_id
`05e64e9ad7ca428f8270e0077c8cbd3d`. l15 fast-forwarded to `e01062d2`. The DB-bound walk stays NOT RUN (lane DB absent);
a future integrated head containing the slice measures it (Codex 0620 §3 correction: batch #8 ran on 0091cc21 without this slice). **176 of 197 is a static registry count, not runtime acceptance.**

**Record correction (Codex production-20260922-0349 §4, accepted by the supervisor; verified at source by P4).** The
Codex-0339 entry above claimed that tenant selection clears the enrolment MFA verification, citing
`domain/platform/memberships.py`. The actual helper path is `principals.enrolled → workspace → API session_select_tenant
(:443–456) → auth.sessions.select_tenant (:1076–1096)`, which reissues the session with
`mfa_verified_at=auth.session.mfa_verified_at` — PRESERVED. `memberships.py:78–88` builds the invitation principal of
`accept_invitation` (its `mfa_verified_at=None` belongs to a freshly accepted invitee), not the tenant-selection reissue.
The claim is struck through above and WITHDRAWN: an already-verified enrolled actor would also have sufficed under the
frozen clock. The clock-advance step-up (`clock.advance(totp.STEP)` then `step_up`) remains a valid, source-corrected fix
(Codex 0349 §3: all 41 assertions unchanged) — a real step-up at a fresh step with the replay / freshness controls
untouched — but it is not the only valid one. The `e7991b5b` commit message carries the superseded rationale; commits are
never amended, so this entry is the correction of record. No code change follows; the `s_users_anonymise` docstring's
freshness statement holds under either reading.

Next dispatch (supervisor): the 21 uncovered operations, plus F-ADM DIN-12's five integration commands once they exist on a
merged tree. Idle, no READY.

### SOP-7 slice 4 — walks for the uncovered operations; latent tranche defects fixed; two catalogue corrections (2026-09-21)

Dispatch: author WALK scenarios for the 21 named uncovered operations, test-only, real positive paths only (no refusal as
success; no direct inserts), counts derived, no exemption changes. Source investigation by four read-only subagents inside
this session (leads, verified by P4 at file:line before authoring; supervisor's rulings 2026-09-21 applied).

**Verified findings that changed the plan.**
- The five `*_publish` commands have no AUDITED positive path through the API: `lifecycle.approve` (domain/policies/
  lifecycle.py:371) and `mapping.approve` (domain/reference/mapping.py:618) publish inside the approval transaction and write
  `<table>.published` there; `lifecycle.publish` (:380–392) and `mapping.publish` (:484–491) return a PUBLISHED version as it
  is (04 §16.5) before any `uow.audit`; `run_command` writes only the idempotency record. `POST …/publish` after approval =
  200 + zero audit rows; on SUBMITTED = 409. No committed API path leaves a version APPROVED-not-PUBLISHED. Treatment
  PROPOSED to the supervisor (Option A: evidence = the `.published` audit under the approval request + `/publish` asserted as
  an idempotent no-audit confirm; B: governed exemption class; C: product no-op audit). **UNCOVERED until ruled:**
  account_mappings_publish, pob_template_versions_publish, rule_set_versions_publish, policies_publish,
  import_mapping_profiles_publish.
- No World actor could approve `config.approve` subjects (Carla has no MFA; Grace / Tomas are tenant_admin → forbidden):
  new World actor **Nora** = `colleague` + `assign("controller")` + `enrolled` (MFA verified at enrolment, preserved through
  the tenant switch). K-02 subjects use `e.marcus`.
- `exceptions_resolve`: **UNCOVERED** — `_cleared` needs a newer SUCCEEDED computation than `last_seen_at`; the only paths
  are seams (direct `raise_exception_item` + `appended`), forbidden by the no-direct-insert rule; no public recompute route.
- `migrations_reconcile`: **UNCOVERED** — needs IMPORTED; the IMPORT job's success over the shipped fixture needs 2023
  periods and the legacy parity templates that no committed HTTP test provisions (only tests/pg/test_migration_capture_pg.py,
  itself NOT RUN); `migrations_import` is walked to its 202 + `migration_batch.import` at acceptance with the job not run.

**Latent defects in tranches 1–3, found in the slice-4 investigation, never run (the DB walk is NOT RUN), fixed here:**
1. `s_pob_template_versions_create` / `_update` sent bare dates to `AwareDatetime` fields → 422 (tranche 1).
2. `s_pob_template_versions_test` had no config test case → 422 CASES_REQUIRED (tranche 1): one passing case on SUB-STD.
3. `s_import_mapping_profiles_create` used `legacy_sku_ssp` (LEGACY_V1) → 422 TEMPLATE_UNKNOWN (tranche 3): CSV v2
   `contracts` with an alias.
4. `s_policies_test` never ran its POLICY_SIMULATION job → submit / withdraw 409 (tranche 3): the job runs, TESTED asserted.
5. `s_journal_runs_create` stored the JOB id as the run id → cancel 404 (tranche 3): run id from `X-Erev-Journal-Run-Id`,
   the JOURNAL_RUN_CALCULATE job run, state `draft` asserted; cancel moved to a second run (FY2026-P08).
6. `s_migrations_create` uploaded the 100-byte SQLITE header fixture → 422 legacy-database-unrecognized (tranche 3): the
   shipped `tests/fixtures/legacy_db/ASC606-shipped-step04.db`.
7. `s_account_mappings_test` ran on a rule-less version → 422 MAPPING_RULES_REQUIRED (tranche 1): rules_create precedes it.
8. The same-customer `s_contracts_create` raises an open COMBINATION_SUGGESTED item, and activation's
   COMBINATION_SUGGESTIONS checklist item fails while one is open (domain/contracts/activation.py
   `combination_suggestions`; `evaluate` → `checklist_problem` 409) → `s_contracts_submit_activation` would have been
   refused (tranche 3): `combination_suggestions_dismiss` now runs between create and submit_activation.

**New walks (public API only).** account_mapping_rules_create (two REVENUE rules) / _delete (the second) before /test;
approvals_bulk_approve (two fresh ROLE_CHANGE requests of Tomas's, bulk-approved by Grace with subject + impact-preview
hashes; every result asserted APPROVED / no problem since HTTP stays 200 on a refused item); combination_suggestions_dismiss
(every suggestion of k02.draft); contracts_regroup (D-98 140 before posting: O2 from a fresh two-line draft to a fresh
one-line draft, 201 `contract.regroup`; pre-posting path only — test_regroup.py is recorded "not run", Q-4 approval shape
open); exceptions_assign / _request_waiver / _dismiss on ONE item from the only public path (a header-only SKU-SSP workbook
→ IMPORT_VALIDATE → INVALID → one BLOCKING IMPORT_NO_DATA_ROWS item; `actions_of` allows DISMISS with a pending waiver:
status open + uncommitted input); exceptions_reprocess (lazy `seat_world(untemplated=("AVM-SEAT-NOMAP",))` in its own
tenant: booking the untemplated product raises PRODUCT_UNMAPPED, the product is mapped first — an unchanged input is a
replay that never resolves — then reprocess 202, the CONTRACT_COMPUTE job run, RESOLVED asserted); journal_runs_submit
(200, approval id kept) / journal_runs_export (Marcus approves — journal.approve, MFA at enrolment, neither submitter nor
calculation author — then export 202 `journal_run.request_export`; the JOURNAL_EXPORT job is not run: no GL adapter);
migrations_profile (202, job run, PROFILED) / migrations_import (202 + audit; body from the fixture's KEY_FIGURES with the
walk calendar id); explain_verify (query: the K-02 contract version's transaction_price recomputed from its trace).

**Catalogue corrections (tests/support/audit_catalogue.py, recorded test-support changes):** `combination_suggestions_dismiss`
row gains its literal `exception_item.dismiss` (a suggestion is an exception_item); `exceptions_request_waiver` row corrected
from `exception_item.waive` (written only on approval) to `approval_request.submit` (approvals/engine.py SUBMIT_ACTION), the
literal the route writes.

**Counts derived from the tree (`.run/p4/sop7/counts-slice4b.txt`):** ROUTES 203, exempt 6, **required 197, authored 190,
WALK 191 entries (no duplicate ids), uncovered 7 = 7 audit + 0 query**: account_mappings_publish,
pob_template_versions_publish, rule_set_versions_publish, policies_publish, import_mapping_profiles_publish (ruling pending),
exceptions_resolve (seam-only), migrations_reconcile (IMPORTED not publicly reachable). Still EXPECTED RED, no xfail;
DB-bound, NOT RUN here (lane DB absent; a future integrated head containing the slice measures it — Codex 0620 §3 correction of the earlier "batch #8 measures it"); the counts are static registry counts, not runtime acceptance.

**Gates on this tree:** `make typecheck` rc=0 (688 files); architecture + catalogue + guides 117 passed; `make lint` in the
commit condition below; the full CPU set before READY (line below).

Full CPU set on `ab80c378` (`.run/p4/sop7/slice4-cpu-full.log`, 22:24:43 → 22:40:17): **"3899 passed, 1 xfailed, 10 errors in
931.53s (0:15:31)"**, ZERO `FAILED` lines; the ten errors are exactly the known lane-DB fixture set (test_cli_idp 2 /
test_cli_operator 1 / test_cli_tenant 1 / test_lists 2 / test_time_zones 1 / test_uow 3). The backup flake did not occur.

### Codex production-20260922-0545 §3 — P4-SOP7-QUERY-TENANT-1 at `ab80c378` (test-boundary defect; fixed; 2026-09-21)

**Finding (accepted; confirmed at source).** `_exercise` took the no-write baseline as `_counts(world.tenant_id)` BEFORE the
scenario ran, while `s_explain_verify` switched to the K-02 tenant inside the scenario (`_engine(w)` sets
`evidence_tenant_id`), so the query operation ran in one tenant and its row counts were compared in another; only the audit
lookup followed the evidence tenant. Not a production-write allegation.

**Fix (test-only).** The tenant the request runs in is selected — and its world prepared — BEFORE the baseline through
`REQUEST_TENANT` (`explain_verify` → the K-02 tenant; every other query operation → the walk's tenant), and the SAME tenant
is compared after the command; the evidence tenant a scenario sets afterwards only scopes the audit lookup. The comparison
is the pure `_changed_tables(before, after, operation_id)` with the `idempotency_record` infrastructure row and the
operation's 04 §1.7 personal rows kept as the only exclusions. Discriminating witnesses: (i) CPU —
`test_query_no_write_check_names_a_mutation` (a non-allowed table delta is named; the idempotency row and the operation's
own personal rows are not; `REQUEST_TENANT` names query operations only) — **1 passed** here; (ii) DB-bound —
`test_query_no_write_check_fails_on_a_request_tenant_mutation` (a `POST /customers` in the K-02 request tenant wrapped
around `explain_verify` must fail the no-write check by name) — NOT RUN (lane DB absent). Module now collects 5 tests.
WALK unchanged (191 entries; 203 / 6 / 197 required = 6 query-class with a no-write check and no audit + 191 audited; 190
authored; 7 uncovered). Commit under the full condition (lint + typecheck + architecture + catalogue) below.

### Pre-READY merge of GREEN main `0091cc21` and the merged-tree conditions (slice 4; 2026-09-21)

Merged as `11c13850` without rebasing: no conflicts; the merge touched no shared test support, catalogue, walk module,
OpenAPI or `uv.lock` (24 commits in; P4 ahead: `ab80c378`, `f87318ff` and the two merges). Merged-tree conditions:
`make lint` rc=0 (200 tagged); `make typecheck` rc=0 (689 files); tests/architecture + catalogue + guides + the CPU witness
118 passed. Counts re-derived on the merged tree (`.run/p4/sop7/counts-merged-0091cc21.txt`): ROUTES 203 / exempt 6 /
**required 197 = 6 query-class (no-write check, no audit) + 191 audited / authored 190 / WALK 191 / uncovered 7**. Full CPU
set on `11c13850` (`.run/p4/sop7/merged-cpu-full.log`, 22:53:01 → 23:04:33): **"3910 passed, 1 xfailed, 10 errors in 689.55s
(0:11:29)"**, ZERO `FAILED` lines; the ten errors are exactly the known lane-DB fixture set (test_cli_idp 2 / test_cli_operator
1 / test_cli_tenant 1 / test_lists 2 / test_time_zones 1 / test_uow 3). Criterion MET. This record-only landing note is
committed under a commit-only condition (lint; the captured summary re-parsed; tree identity = the record alone; the walk
module and the catalogue unchanged since before the run began).

### LANDED: SOP-7 slice 4 + QUERY-TENANT-1 (sprint/l15@d12c14d7 → main 872a0d61; 2026-09-22)

Supervisor's line, quoted: "02:33:39 p4s4 PASS: merged p4s4 sprint/l15@d12c14d7 onto 0091cc21: 872a0d61 | POSTCHECKS:
typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS". Main `872a0d61` is GREEN; l15 fast-forwarded to it. Merged ≠ accepted:
the DB-bound walk is NOT RUN; a future integrated head containing the slice measures it. Wording correction (Codex
production-20260922-0620 §3): the three slice-4 entries above that said "batch #8 measures it" now read "a future integrated
head containing the slice measures it" — batch #8 ran on main `0091cc21`, which did not contain this slice.

**Batch #8 finding (WALK-DB-1).** Integrated batch #8's `ci` on main `0091cc21` was the first DB execution of the SOP-7 walk
(my tranches 1–3 with the 0223 / 0339 fixes): **main's walk had ~70 failing scenario lines at batch #8; the eight latent
defects fixed in slice 4 were a subset.** The by-design lines were confirmed ("audited operations without a walk scenario
(20 of 197 required; 176 authored)"; "AI proposal lifecycle (pending on lane F-AIX)"). The read-only diagnosis (WALK-DB-1,
supervisor-accepted) classified every line: two PRODUCT defects — MAIN DEFECT 4 (`POST /account-mappings` 500: a naive
`effective_from` accepted by `AccountMappingIn.effective_from: datetime | None` reaches `erev_engine/canonical.py:82–83`
through the audit path; owner P4, fixed in slice 5) and P8's PRV-07a (`users_anonymise` 403: the erasure UPDATE falls
outside the DB-13 column grant; P8's line) — plus MAIN DEFECT 3's cascades (classify → preview / submit / withdraw); every
other line a WALK defect or its cascade (see slice 5).

### Slice 5 — COMMIT A: the WALK-DB-1 walk fixes + SOP7-SEAM-EXC-1 (test-only; 2026-09-22)

Every fix below answers a batch #8 line on main `0091cc21`, diagnosed read-only at file:line (WALK-DB-1, supervisor-accepted)
and applied to `test_audit_coverage.py` only. **Headers / state (systematic):** If-Match through `_etag_of` at call time on
fx_rate_set_versions_submit / _withdraw, roles_propose_change and ssp_book_versions_submit (routes with `precondition="row"`
answered 428; the four GET routes exist); config_test_cases_delete carries If-Match from the update response's ETag (no GET
by id); users_update re-reads its ETag (the resend had moved the row → 412). **CSRF:** `s_me_mfa_confirm` re-reads the
rotated session through `support.principals.refreshed` (the CSRF token is derived from the session token; the confirm body
carries none → the two leo 403s and the logout cascade). **Checklist:** `_open_item` filters the E-60 literals NOT_STARTED /
IN_PROGRESS / FAILED (the old "OPEN" / "PENDING" never occur → StopIteration ×2); sign by Nora on a MANUAL item and waive by
Nora, both with the period-state If-Match; a second MANUAL template (RECON-AR) so sign and waive each have an item.
**Actors:** tenant_snapshots_request by Nora (tenant.snapshot needs MFA; Carla has none); users_suspend / _reactivate on a
fresh ACTIVE colleague (the invited probe never accepted). **Lifecycle:** the DQ rule case expects `{"matched": True}` (a
condition-less rule matches everything) and the delete of a throwaway rule moves BEFORE /test (CONTENT_CHANGED);
imports_create runs the chained IMPORT_DIFF job and asserts DIFF_READY (submit needs it); imports_cancel imports a distinct
workbook (identical bytes are a duplicate-import). **Access reviews:** the complete loop skips only `decision != "PENDING"`
(the literal is truthy); confirm_revocation revokes a viewer assignment of Sam first (approved by Grace, revoked by Tomas).
**Role assignments:** created for Sam and approved by Grace before revoke (the row exists only on approval). **Bodies:**
approval delegation of `access.approve`; dimension code `region` (+ both value paths, value code `emea`); legacy-parity preset
`{"scope": "TENANT"}`; policies_update effective_from at the entity's local midnight (`2026-10-01T04:00:00Z`, T-PLT-32);
policy override on the CONTRACT-level `step1.term_with_termination_rights = STATED_TERM`; rule_sets_evaluate with empty
facts (DATA_QUALITY takes none); account_mappings_create with an aware datetime (hygiene — the 500 is MAIN DEFECT 4);
SSP entries read from `entries`; books_update takes its ETag from the list item (no GET /books/{code}). **K-02:** the draft
keeps its external id across replace-draft (EXTERNAL_ID_FIXED) and carries a `document_ref` (SOURCE_REFERENCE); a REVIEWED
COLLECTIBILITY judgement (approved by Marcus) and a probable COLLECTIBILITY_ASSESSED event precede submit-activation
(STEP1_RECORD); the hold id is the HOLD_APPLIED event id; the SSP calculator run id comes from
`X-Erev-Ssp-Calculator-Run-Id`, its job runs, and the draft version carries a `version_label`.

**SOP7-SEAM-EXC-1 (supervisor ruling of 2026-09-22; for Codex review at this commit).** Limited to periods_request_lock,
periods_request_permanent_lock and periods_request_reopen, run on FY2026-P01 (earliest first, SM-07): start-close again after
the cancel, the remaining checklist items waived by Nora over public routes, then ONLY the two gate facts a lock decision needs
seeded through the close lane's committed helpers `support.close_world.acknowledged_run_for` and
`reviewed_reconciliations_for` under a system session built as `close_world.system_session` does; request-lock by Maya;
approval by Nora (MFA controller, distinct from the requester) → CLOSED asserted; request-permanent-lock and request-reopen
by Nora. Rationale, verbatim: "the audited subjects are the lock / permanent-lock / reopen commands; the gate facts are
preconditions produced by an external GL acknowledgement for which the product deliberately exposes no route; the seeds are
the close lane's reviewed helpers"; and "the reconciliation-gate parameter is tenant-publishable but period-pinned
(effective only from a future period's first day), so it cannot apply at the walk's lock instant — verified at file:line"
(registry/platform.py:56–78; registry_versions.py:350–394; gates.py:575–586). No policy is published as a no-op step. The
evidence covers the lock COMMANDS, not the production of gate facts. No other direct insert exists in the walk.

**Unchanged by design (named failures until their product lines land):** users_anonymise (P8 PRV-07a); modifications_classify
/ _preview / _submit / _withdraw (MAIN DEFECT 3). Counts (`.run/p4/slice5/counts-commit-a.txt`): 203 / 6 / 197 (6 query-class
+ 191 audited) / 190 authored / WALK 191 / 7 uncovered — unchanged. DB-bound, NOT RUN (lane DB absent). Condition: lint +
typecheck + tests/architecture + catalogue + the CPU witness, below.

### Slice 5 — COMMIT B: MAIN DEFECT 4, product (2026-09-22; owner: the supervisor, RFD-7 has no active lane)

**Defect (registered by the supervisor as MAIN DEFECT 4 from batch #8).** `POST /account-mappings` answered 500 to a
schema-valid body: `AccountMappingIn.effective_from: datetime | None` (schemas/account_mappings.py:36) accepted
`"2026-01-01"` as a NAIVE datetime; `create_account_mapping_version` (domain/reference/commands.py:2478–2530) stored and
audited it, and the audit canonicaliser (`erev_engine/canonical.py:82–83`) raised `ValueError("canonical encoding requires a
timezone-aware datetime")`. `AccountMappingUpdateIn.effective_from` (:51) carried the same latent defect. Every committed test
sent an aware value, so the naive path was never exercised.

**Fix (conformance to the governed type; no docs row — 04 SC-V :277 governs `effective_from timestamptz`).**
`AwareDatetime | None` on both models (the `pob_templates.py:95` / `imports.py:257` shape): a naive value now answers 422
`validation-failed` at request validation; aware values and an absent value behave as before. **CPU witness**
`tests/unit/test_account_mapping_schemas.py` (8 passed here): `"2026-01-01"` and `"2026-01-01T00:00:00"` refused on both
models with pydantic type `timezone_aware` at `effective_from`; `Z`, `+00:00` and `-04:00` forms accepted with tzinfo; absent
stays optional. `make openapi` regenerated: **no diff** — pydantic renders `AwareDatetime` as the same `date-time` string
format, so `docs/api/openapi.json` and the frontend schema are unchanged. The walk's own body already sends an aware value
(COMMIT A). Condition: lint + typecheck + tests/architecture + catalogue + the witness, plus the FULL CPU set because a
product schema changes (line below).
Full CPU set on the COMMIT B tree (`.run/p4/slice5/commit-b-cpu-full.log`, 02:42:03 → 02:52:04): **"3918 passed, 1 xfailed,
10 errors in 585.21s (0:09:45)"**, ZERO `FAILED` lines; the ten errors are exactly the known lane-DB fixture set. Fast condition
on the same tree: lint rc=0 (200 tagged), typecheck rc=0 (689 files), architecture + catalogue + guides + witnesses 126 passed,
the walk module collects 5. Reporting defect (P4, again): the run ENDED at 02:52:04 and was reported at ~03:46 — the Monitor
completion notice did not wake the idle lane (as the lane-wide rule warned); corrective: hold expected ENDs with foreground
blocking waits (≤ 10 min, re-issued within the turn), never a background watch alone. Committed under the commit-only gate
(`.run/p4/slice5/commit-b-gate.sh`: summary re-parsed, 0 FAILED, the known ten, tree = schema + witness + record, code files
unchanged since before the run, lint rc=0).

### SOP7-PUBLISH-CONFIRM-1 — docs-first line (build-spec 1.16; 04 1.83; 2026-09-22; for Codex review before any code)

Numbers assigned by the supervisor (1.16 verified free, 1.15 F-ADM unlanded; 04 1.83 reserved then CONFIRMED for the
note-only revision, 1.81 / 1.82 unlanded). Governing text confirmed identical on both branches (BUILD_SPEC.md:10970 =
docs/build-spec/11-foundation-platform.md:2965, md5-identical). Changes, docs only:
- `docs/build-spec/00-header.md`: the `| Revision |` summary now leads with 1.16 (lane P4, SOP7-PUBLISH-CONFIRM-1) and the
  revision log gains row 1.16 after 1.14 — class (d) "idempotent confirms": the five `*_publish` commands stay REQUIRED; their
  required same-transaction `audit_event` is the APPROVAL transaction's `<table>.published` row under the FINAL approving
  request's `X-Request-Id` and `actor_kind`; the confirm's own FRESH request writes no transition audit and only
  `idempotency_record`; coverage needs the Codex 0527 §2 correlation (tenant / table / version-row UUID / approval id /
  approving request id / SUCCESS APPROVED → PUBLISHED event and actor; a distinct fresh confirmation returning the same
  PUBLISHED version; a bounded subject state unchanged); the `APPROVED`-left-unpublished branch is not covered; no blanket
  exemption; the publication literal is f-string-built and verified at runtime, not by `action_literals()`.
- `docs/build-spec/11-foundation-platform.md:2965`: the class-(d) sentence appended to the SOP-7 Acceptance bullet (the
  same content, in the Acceptance's own words, resolving the "same transaction … response X-Request-Id … actor_kind of
  the caller" literal Codex 0527 cited).
- `docs/04-DATA_MODEL.md`: `| Revision |` leads with 1.83; row 1.83 after 1.80; the §16.5 publish note (rev 1.2) stated for
  `/publish` on API-R-20 (account mappings), API-R-24 (POB templates), API-R-25 (rule sets) and API-R-43 (mapping profiles):
  the final approval publishes in the approval transaction (`lifecycle.approve` → `publish`; `mapping.approve` → `publish`),
  so `/publish` stays accepted for a version left APPROVED and returns 200, unchanged and without a transition audit, for a
  version its approval already published. Notes only; no schema change.
- `docs/BUILD_SPEC.md` regenerated by `research-harness/buildspec/merge_buildspec.py` (never by hand); `--check` rc 0.
No code in this commit: the catalogue `confirm` kind, the CTL-038 assertion change and the five walks (drafted in
`.run/p4/sop7/option-a/`, with the Codex 0527 §2 witness) follow as the code commit AFTER Codex reviews this line.

### Slice 5 pre-READY merge of GREEN main `ee6ebea7` and the merged-tree conditions (2026-09-22)

Merged as `c091f701` (no rebase; `ae0f1af7` and newer not taken). Three expected conflicts resolved as ruled: the 04 and
build-spec 00-header revision tables as descending unions with nothing renumbered and both sides' rows kept (04 summary
1.84 (F-CTR), 1.83 (P4), 1.82 (P1), 1.80 …; rows 1.84 / 1.83 / 1.82; header summary 1.16 (P4) above main's 1.14; rows 1.14
then 1.16); `docs/BUILD_SPEC.md` never resolved by hand — regenerated by `merge_buildspec.py` on the merged sources
(`--check` rc 0). Everything else auto-merged (main's 0070 / 0071 migrations and every lane landed since `872a0d61`).
Merged-tree conditions: `make lint` rc=0 (200 tagged); `make typecheck` rc=0 (693 files); tests/architecture + catalogue +
guides + the two witnesses 126 passed; **SOP-7 pins re-measured**: the merged OpenAPI has 203 command operations = the
catalogue's 203 rows (no op missing from the catalogue, no row without an op), exempt 6, required 197 = 6 query-class + 191
audited — the landed pins (203 / 197) hold; counts 190 authored / WALK 191 / 7 uncovered (the five *_publish pending the
SOP7-PUBLISH-CONFIRM-1 code follow-on, exceptions_resolve, migrations_reconcile) — `.run/p4/slice5/counts-merged-ee6ebea7.txt`.
Full CPU set on `c091f701` (`.run/p4/slice5/merged-cpu-full.log`, held with foreground waits, ended 04:05:55): **"3966 passed,
1 xfailed, 10 errors in 676.31s (0:11:16)"**, ZERO `FAILED` lines; the ten errors exactly the known lane-DB fixture set —
criterion MET (a CPU-criterion result, not a full pass). DB-bound walk NOT RUN; a future integrated head containing the slice
measures it. Record-only commit under the commit-only gate (summary re-parsed; tree = record alone; code files unchanged
since before the run; lint).

### Slice 5 — third pre-READY merge (GREEN main `66d1723f`, DIN-12) and the merged-tree conditions (2026-09-22)

The READY at `586df334` was not queued: its docs/BUILD_SPEC.md conflicted with main `66d1723f` (F-ADM DIN-12), which the
chain resolver refuses by rule (fclo5 precedent — a generated file is regenerated, never resolved), so a third pre-READY
merge was ruled. Merged as `2a4c70c2` on the supervisor's GREEN word ("04:19:54 fdin12 PASS … aggregate=PASS"); main's newer
head not taken. Conflicts: the 04 summary line (main's line with the P4 1.83 entry restored before 1.82; the rows had
auto-merged), the build-spec 00-header summary (1.16 (P4); 1.15 (F-ADM); 1.14 …) and rows (1.15 then 1.16), and
`docs/BUILD_SPEC.md` regenerated by `merge_buildspec.py` on the merged sources (`--check` rc 0). Disclosure: the shell chain
skipped the merge's commit step once (a whitespace-sensitive `wc -l` comparison), leaving the resolved merge staged; no
unresolved path remained and the same prepared message was committed — no content change, no hand edit.

Merged-tree conditions: `make lint` rc=0 (203 tagged); `make typecheck` rc=0 (701 files); tests/architecture + catalogue +
guides + the two witnesses 126 passed. **SOP-7 pins re-measured on the merged tree — main's after DIN-12:** the merged
OpenAPI has **209** command operations = the catalogue's 209 rows (no op missing, no orphan row), exempt 6, **required 203 =
6 query-class + 197 audited**, with F-ADM's six DIN-12 operations REQUIRED; this line touches no pin file. Counts re-derived
(`.run/p4/slice5/counts-merged-66d1723f.txt`): **authored 190 / WALK 191 / uncovered 13**, named: account_mappings_publish,
pob_template_versions_publish, rule_set_versions_publish, policies_publish, import_mapping_profiles_publish (the
SOP7-PUBLISH-CONFIRM-1 code follow-on, after Codex reviews the docs line); exceptions_resolve (seam-only);
migrations_reconcile (IMPORTED not publicly reachable); and DIN-12's six — integrations_create, integrations_update,
integrations_test, integrations_sync, webhooks_receive, external_ids_create — whose walks are P4's in a later slice.
**Known expectation:** the DB-bound `test_ctl_038_every_command_route_writes_audit` FAILS by design at batch #9 while any
required operation lacks a scenario — these thirteen. Full CPU set on `2a4c70c2` (`.run/p4/slice5/merged3-cpu-full.log`, held
with foreground waits, ended 04:36:05): **"4049 passed, 1 xfailed, 10 errors in 722.87s (0:12:02)"**, ZERO `FAILED` lines; the
ten errors exactly the known lane-DB fixture set — criterion MET (a CPU-criterion result, not a full pass). DB-bound walk NOT
RUN. Record-only commit under lint + the guards + tests/architecture and the commit-only gate (summary re-parsed; tree = the
record alone; code files unchanged since before the run).

**DEVIATION recorded (supervisor's classification, 2026-09-22).** Committing the merge `2a4c70c2` by a re-issued command after
the chain's commit step was skipped is a deviation from the standing rule ("after a failed or skipped commit step, never
commit by hand; a commit-only condition re-checks the captured result and tree identity"). The content was the prepared
resolution, so no change was needed; no amend, reset or re-merge. Post-hoc commit-only re-check on `2a4c70c2`, quoted:
1. `git log -1 --format=%P 2a4c70c2` = `586df334 66d1723f` (exactly the previous head and the GREEN head);
2. conflict markers over the tracked files of `2a4c70c2`: 0 files with `<<<<<<< ` or `>>>>>>> ` (a lone `=======` is legitimate
   Markdown);
3. `merge_buildspec.py --check` rc 0 — "docs/BUILD_SPEC.md equals a fresh merge" (BUILD_SPEC and its sources identical between
   `2a4c70c2` and HEAD);
4. `git diff --name-only 66d1723f 2a4c70c2` = exactly the eight paths this line carries vs main: `backend/erev_api/schemas/
   account_mappings.py`, `backend/tests/domain/platform/test_audit_coverage.py`, `backend/tests/unit/test_account_mapping_schemas.py`,
   `docs/04-DATA_MODEL.md`, `docs/BUILD_SPEC.md`, `docs/build-spec/00-header.md`, `docs/build-spec/11-foundation-platform.md`,
   `docs/reviews/loop/prod/P4-doctor.md` — nothing else;
5. `git status --porcelain` empty; no MERGE_HEAD.
Chain rule for every later gate: counts are compared numerically (`[ "$(wc -l < f | tr -d ' ')" -eq N ]`), never as strings; a
skipped step STOPs the chain and is reported before anything else runs.

### LANDED: slice 5 (COMMIT A + SOP7-SEAM-EXC-1, COMMIT B MAIN DEFECT 4) + docs-first 1.16 / 1.83 (sprint/l15@032a9c8b → main 4dba2ee1; 2026-09-22)

Supervisor's line, quoted: "05:06:56 p4s5b PASS: merged p4s5b sprint/l15@032a9c8b onto cfeb2ee4: 4dba2ee1 | POSTCHECKS:
typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS". The 04 revision table was resolved by merge-revrows; main `4dba2ee1` is
GREEN; l15 fast-forwarded to it. **Merged ≠ accepted:** MAIN DEFECT 4 is SOURCE-FIXED (the AwareDatetime schemas) — its DB
acceptance (`account_mappings_create` / `_update` no longer 500) is measured at batch #9; the slice-5 walk fixes and
SOP7-SEAM-EXC-1 are measured at batch #9, where `test_ctl_038_every_command_route_writes_audit` FAILS by design on the
thirteen uncovered operations; the docs-first 1.16 / 1.83 await Codex's review. Next: the SOP7-PUBLISH-CONFIRM-1 code
follow-on only after Codex reviews `bbca615a`; then the six DIN-12 integration walks as a later slice (proposal read-only
meanwhile).

### Slice 6 — docs-first (build-spec rev 1.19): the webhook receiver's SYSTEM actor (2026-09-22)

Supervisor ruling on the slice-6 proposal (the six DIN-12 integration walks): GO, independent of the SOP7-PUBLISH-CONFIRM-1
follow-on. The SYSTEM-actor allowance for `webhooks_receive` is approved, limited to that operation and named in the failure
message (the REFUSAL_EVIDENCE pattern), and made explicit docs-first: build-spec header **rev 1.19** (assigned by the
supervisor, verified free — 1.17 held for F-CTR, 1.18 T1's unlanded) adds one sentence to the SOP-7 Acceptance bullet
(`docs/build-spec/11-foundation-platform.md`): for the signature-verified webhook receiver the recorded actor is the tenant's
system principal, `actor_kind` SYSTEM (the unauthenticated receiver's caller is the adapter; `system_principal` at
api/v1/integrations.py:469/:509 by F-ADM's design). `docs/BUILD_SPEC.md` regenerated by `merge_buildspec.py` (`--check` rc 0).
Pre-condition for re-roling ivy, quoted (read-only grep of the walk): ivy is used only at the World field (:163), her build
(:200 `holding(...)`, no MFA), the World constructor (:218) and the two webhook-endpoint scenarios (:695, :702 — positive
paths); the denied-commands test uses `vera` (a viewer); no scenario relies on ivy lacking MFA or the integration_admin role →
ivy becomes an ENROLLED integration_admin in the code commit.

### Slice 6 — code: the six DIN-12 integration walks (test-only; 2026-09-22)

Walks, positive paths only, F-ADM's API-test shapes (tests/api/test_integrations_api.py): **integrations_create** — Ivy (now an
ENROLLED integration_admin: `integration.manage` is an MFA permission, auth/permissions.py:147 / dependencies.py:353–362) posts a
SALESFORCE INBOUND connection on the app's mounted mock routes (`mocks.MOCKS_PREFIX + sf_mock.PREFIX`; the adapter is registered
by create_app, main.py:124; the mock routes mount for env test, adapters/mocks/__init__.py:19) with `secret_ref` naming an
environment variable → 201. **integrations_update** — PATCH `{"status": "ACTIVE"}` with If-Match → 200 (also the precondition of
sync and webhook). **integrations_test** — POST /test inside `_integration_hooks`: the composition hooks of the adapter framework,
not DB seams (supervisor ruling of 2026-09-22) — the secret reference's environment variable set to the mock's FIXTURE value
(adapters/mocks/salesforce.py:46, never a credential) and restored afterwards; the adapter's HTTP client replaced by the
in-process ASGI client over the mock routes (`sync.register_http_client_factory`) and restored in the finally; no socket, no
network — SUCCESS asserted. **integrations_sync** — 202 JobOut + `sync_run.request` at acceptance; the SYNC_RUN job is NOT run
(it would ingest the mock's orders), as for migrations_import. **webhooks_receive** — the notification body signed by the mock's
own `/webhooks/sign` helper and posted unauthenticated to `/webhooks/SALESFORCE/{receiver_id}` → 202; its audit is written
under the tenant's system principal, so the walk admits `actor_kind` SYSTEM for this one operation (`SYSTEM_ACTOR`, named in
the failure message; BUILD_SPEC rev 1.19). **external_ids_create** — Maya (masterdata.maintain) links the walk's customer to
`SF-ACC-SOP7-001` on the connection → 201. Ivy's re-role: no scenario relied on her lacking MFA (grep quoted above).
Counts (`.run/p4/slice5/counts-slice6.txt`): ROUTES 209 / exempt 6 / required 203 (6 query-class + 197 audited) / **authored
196 / WALK 197 / uncovered 7** — the five `*_publish` (SOP7-PUBLISH-CONFIRM-1 code follow-on, after Codex reviews the docs
line), exceptions_resolve, migrations_reconcile. DB-bound, NOT RUN (lane DB absent); the CTL-038 walk still FAILS by design while
those seven lack a scenario. Condition: lint + typecheck + tests/architecture + catalogue, below; full CPU before READY.

### Slice 6 pre-READY merge of GREEN main `dfc276f9` and the merged-tree conditions (2026-09-22)

Merged as `e073fd18` (parents `3df9a2c3` `dfc276f9`; no rebase; p1alert1 not taken): no conflicts — every path auto-merged;
`docs/BUILD_SPEC.md` checked against a fresh merge of the merged sources (`merge_buildspec.py --check` rc 0; no regeneration
needed). Merged-tree conditions: `make lint` rc=0 (203 tagged); `make typecheck` rc=0 (701 files); tests/architecture +
catalogue + guides + witnesses 128 passed; SOP-7 pins re-measured: the merged OpenAPI has 209 command operations = the
catalogue's 209 rows (no op missing, no orphan row), exempt 6, required 203 = 6 query-class + 197 audited; counts
(`.run/p4/slice5/counts-merged-dfc276f9.txt`) **authored 196 / WALK 197 / uncovered 7** (the five `*_publish` pending the
SOP7-PUBLISH-CONFIRM-1 code follow-on after Codex reviews `bbca615a`; exceptions_resolve; migrations_reconcile) — the CTL-038
walk FAILS by design while those seven lack a scenario. Full CPU set on `e073fd18` (`.run/p4/slice5/merged6-cpu-full.log`,
held with foreground waits, ended 05:37:53): **"4057 passed, 1 xfailed, 10 errors in 699.62s (0:11:39)"**, ZERO `FAILED`
lines; the ten errors exactly the known lane-DB fixture set — criterion MET (a CPU-criterion result, not a full pass).
DB-bound walk NOT RUN; a future integrated head containing the slice measures it. Record-only commit under the commit-only
gate (summary re-parsed; tree = the record alone; code files unchanged since before the run; lint; tests/architecture + guides).

### LANDED: slice 6 (the six DIN-12 integration walks) + build-spec 1.19 (sprint/l15@f9d06893 → main 803a3109; 2026-09-22)

Supervisor's line, quoted: "06:24:12 p4s6 PASS: merged p4s6 sprint/l15@f9d06893 onto 23f30fec: 803a3109 | POSTCHECKS:
typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS". Clean; main `803a3109` is GREEN; l15 fast-forwarded to it; build-spec
1.19 is on main. **Merged ≠ accepted:** the six DIN-12 walks are DB-bound and measured at batch #9, where
`test_ctl_038_every_command_route_writes_audit` FAILS by design on the seven still uncovered (the five `*_publish`,
exceptions_resolve, migrations_reconcile). Next: the SOP7-PUBLISH-CONFIRM-1 code follow-on only after Codex reviews
`bbca615a`; nothing else is routed to this lane until then.

### Slice 7 — exceptions_resolve through public routes (test-only; 2026-09-22)

Supervisor rulings on the read-only verdicts: exceptions_resolve FEASIBLE with the one-second FrozenClock step APPROVED (the
test controlling its own time input, not a DB seam; the whole walk already runs on that clock); migrations_reconcile NOT
FEASIBLE now — stays UNCOVERED, disclosed (the committed parity-template helper is a direct-insert seam; the SKU-SSP coverage
across fixture families is unproven; the IMPORT and reconcile job outcomes are unproven on any real database; no exception
offered; revisit after an integrated batch proves the IMPORT job). **The walk:** `s_exceptions_resolve` books the seat world's
SECOND untemplated product (`AVM-SEAT-NOMAP-2`, so slice 5's reprocess walk is not pre-empted) → one PRODUCT_UNMAPPED item on
its own group (ENGINE items dedupe per code and group, compute_job.py:347); maps the product publicly (PATCH /products default
template); steps the FrozenClock by ONE second and ASSERTS (a) the step is exactly one second and (b) Tomas's step-up, recorded
at the world build (`ids["tomas.stepped_up_at"]`), is still inside BS1-D-19's five-minute window (STEP_UP_WINDOW) — no control
window is skipped; every audited timestamp comes from the advanced clock, nothing hand-set; then POST /contracts/{id}/replace-
draft (same body, If-Match) recomputes the provisional version (contracts/commands.py:578–600) so the SUCCEEDED head
(computation.py:1027), created after the item's `last_seen_at`, clears it (`_cleared`, imports/exceptions.py:677–682) —
asserted through `available_actions` ∋ RESOLVE — and POST /exceptions/{id}/resolve → 200, audit exception_item.resolve.
No direct insert. DB-time residual, NOT RUN (batch #9): whether the refused first compute leaves a DRAFT that replace-draft
accepts. Counts (`.run/p4/slice5/counts-slice7.txt`): ROUTES 209 / exempt 6 / required 203 / **authored 197 / WALK 198 /
uncovered 6** — the five `*_publish` (SOP7-PUBLISH-CONFIRM-1 code follow-on after Codex reviews `bbca615a`, to be rebased onto
this head) and migrations_reconcile. Condition: lint + typecheck + tests/architecture + catalogue, below; full CPU before READY.

### Slice 7 pre-READY: the named GREEN head `803a3109` is an ancestor — no merge; the full CPU set on `6294a5e8` (2026-09-22)

The supervisor named `803a3109` (p4s6, this lane's slice-6 landing) as the GREEN head; `git merge-base --is-ancestor 803a3109
HEAD` holds, so the pre-READY merge is a no-op and was skipped (main's newer `16c6b790`, post-checks pending, not taken). The
per-commit condition had passed at `6294a5e8`; the READY needs the full set: **"4115 passed, 1 xfailed, 10 errors in 760.02s
(0:12:40)"** (`.run/p4/slice5/slice7-cpu-full.log`, held with foreground waits, ended 06:52:42), ZERO `FAILED` lines; the ten
errors exactly the known lane-DB fixture set — criterion MET (a CPU-criterion result, not a full pass). Counts unchanged
(`.run/p4/slice5/counts-slice7.txt`): 209 / 6 / 203 required / authored 197 / WALK 198 / uncovered 6 (the five `*_publish`,
migrations_reconcile). DB-bound walk NOT RUN; a future integrated head containing the slice measures it (batch #9 also
measures the slice-7 DB-time residual). Wording correction (supervisor): the SOP7-PUBLISH-CONFIRM-1 code follow-on will be
MERGED onto this head, never rebased (the standing git rule). Record-only commit under the commit-only gate (summary
re-parsed; tree = the record alone; code files unchanged since before the run; lint; tests/architecture + guides).

### LANDED: slice 7 (exceptions_resolve) (sprint/l15@ad6ad1ed → main f605e76d; 2026-09-22)

Supervisor's line, quoted: "08:03:53 p4s7 PASS: merged p4s7 sprint/l15@ad6ad1ed onto fd585009: f605e76d | POSTCHECKS:
typecheck=rc0 cpu=rc0 selection=rc0 aggregate=PASS". Clean; main `f605e76d` is GREEN; l15 fast-forwarded to it. Merged ≠
accepted: the exceptions_resolve walk is DB-bound and measured at batch #9 (with its stated residual); CTL-038 still fails by
design until the confirm walks land.

### SOP7-PUBLISH-CONFIRM-1 — code follow-on (test-only; Codex production-20260922-1458 §1 design credit for `bbca615a`; 2026-09-22)

Codex's requirements → the witness assertions, by name:
- "all 5 routes remain REQUIRED" → `required_operations()` = ROUTES − SOP_7_EXEMPT is unchanged (test_audit_catalogue
  `test_sop_7_required_operations_exclude_class_a`: 209 − 6 = 203); the five rows carry evidence kind `confirm`
  (`_confirm(op, "<table>.published", note)`), pinned `by_evidence["confirm"] == 5` in `test_inventory_shape_for_the_database_walk`.
- "approval-time publication in the same UOW" and "RETAIN the tenant / table / version / approval / final-request / actor
  correlation; SUCCESS and APPROVED → PUBLISHED audit" → `_exercise`'s confirm branch reads `_audit_events(tenant, approving
  X-Request-Id)` and requires a row with action `<table>.published`, object_type = the table, object_id = the approval's
  `subject.id` (the version row), approval_request_id = the business approval id, actor_id = the approver's user id, outcome
  SUCCESS; and, in the SAME request, a `<table>.approved` row for the same object_id (the APPROVED → PUBLISHED transition is the
  approval's own unit of work). The facts come from `_confirm_publish` (CONFIRM_KEYS), which reads the approval detail before
  approving and keeps the approving call's X-Request-Id.
- "a DISTINCT fresh non-replay confirmation with unchanged status / row_version / updated_at / content hash" → the confirm POST
  is a fresh request (`post()` sends a fresh `Idempotency-Key`, support.principals.cookie_headers), must answer 200 with
  `status == "PUBLISHED"` and the SAME version-row id, writes ZERO audit rows under its own request id (`_audit_rows`), and
  `_bounded_state` (status, row_version, updated_at, content_sha256) is equal before and after (`confirm.before` vs
  `confirm.after`).
- "PRESERVE the existing publication prerequisites, the account-mapping lint and the separate APPROVED-left-unpublished branch" →
  no product code changes; each walk approves a SUBMITTED version (the prerequisites and the mapping re-lint run inside
  approve/publish as before) and only then confirms; the APPROVED-left-unpublished `publish` branch is NOT what these walks
  witness (stated in the confirm branch's comment and here).
- "the catalogue class and the public correlation walks are implementation owed" → this commit: `confirm` kind + the five walks
  (account_mappings_publish, rule_set_versions_publish, pob_template_versions_publish, import_mapping_profiles_publish; and
  policies_publish, which reopens the withdrawn version — PATCH effective_from → the POLICY_SIMULATION job → submit — before
  approval and confirm, ahead of the legacy-parity preset). The literals `<table>.published` are f-string-built by
  `lifecycle.transition` (verified by the walk at runtime; the unit scanner checks `.endswith(".published")` for confirm rows).
Touched test modules alone, quoted: tests/unit/test_audit_catalogue.py + the walk's CPU witness "11 passed in 2.40s"; the walk
module collects 5. Counts (`.run/p4/slice5/counts-confirm.txt`): ROUTES 209 / exempt 6 / required 203 / **authored 202 / WALK
203 / uncovered 1** (migrations_reconcile — not feasible now, ruled). DB-bound, NOT RUN. Condition: lint + typecheck +
tests/architecture + catalogue below; the full CPU set before READY.

Full CPU set on `246bee5e` (`.run/p4/slice5/confirm-cpu-full.log`, held with foreground waits): "4121 passed, 1 xfailed,
10 errors in 769.21s (0:12:49)"; 0 FAILED; the errors are exactly the known ten (test_cli_idp 2 / test_cli_operator 1 /
test_cli_tenant 1 / test_lists 2 / test_time_zones 1 / test_uow 3 — the lane-DB-absent set). Committed under the commit-only
gate (`.run/p4/slice5/ready8-gate.sh`: summary re-parse, 0 FAILED, known ten, tree = record only, the three test files predate
the run, lint, architecture + guides). READY follows with a fresh merge-tree vs main.

### Lane FIX-C — SOP-7: class (c) names the saved-view operations; the caller-kind check reads "at least one" (build-spec 1.25; rulings R-14, R-15; 2026-09-29)

Entered by lane FIX-C (the batch #9 repair of `test_ctl_038_every_command_route_writes_audit`), because the SOP-7 acceptance
names the exempt operations "in the test's failure message and in the lane record".

- **R-14 (docs first; build-spec header rev 1.25, fragment 11).** Exemption class (c) is defined by the 04 §1.7 AUD-OPS class,
  and 04 T-PLT-37 classes `saved_view` AUD-OPS. Its enumeration had omitted `saved_views_create`, `saved_views_update` and
  `saved_views_delete` (`POST /saved-views`, `PATCH` / `DELETE /saved-views/{id}`); the catalogue inventoried them as
  unverified `audit_event` routes and the walk reported "no audit_event" for each. They are now `query` routes
  (`QUERY_EXEMPT`: nine operations). What the walk permits for the three: zero `audit_event` rows, the caller's own
  `saved_view` row (`PERSONAL_TABLES`) and the `idempotency_record` row — no other tenant-scoped table may change its row count.
- **R-15 (no document change).** The acceptance reads "writes at least one `audit_event` in the same transaction, with `action`
  matching …, `request_id` equal to the response `X-Request-Id`, and `actor_kind` of the caller". The walk required EVERY row
  of the request to carry the caller's kind and so refused `contracts_replace_draft`, `contracts_distinct_review` and
  `judgements_submit`, whose commands append one contract event as the SYSTEM principal beside the caller's rows: the
  `EVENT_VOIDED` of a replaced draft (04 §16.1; `domain/contracts/commands.py:629`) and the `HOLD_APPLIED` of the SYSTEM
  recognition hold a pending judgement puts on an ACTIVE contract (REQ-POL-010; `domain/contracts/holds.py:363`). The check
  is now the acceptance's: at least one row of the request with the caller's `actor_kind` (SYSTEM for `webhooks_receive`,
  rev 1.19, unchanged); the action pattern is still checked on every row.
