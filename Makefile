# eRev Cloud entry points (docs/dev-guide.md §4).
# GNU Make 3.81 compatible: no .ONESHELL, no --output-sync, no $(file ...), no grouped targets (DG-ENV-05).
# Every target is phony, runs from the repository root, exits non-zero on failure and ends with
# "OK <target>" or "FAIL <target>: <reason>" (DG-MK-00a).

SHELL := /bin/bash

PY := backend/.venv/bin/python
EREV := backend/.venv/bin/erev
PYTEST := backend/.venv/bin/pytest
ALEMBIC := backend/.venv/bin/alembic
NODE_BIN := frontend/node_modules/.bin
RUFF := backend/.venv/bin/ruff
MYPY := backend/.venv/bin/mypy

export TMPDIR := $(CURDIR)/.run/tmp
export PYTHONDONTWRITEBYTECODE := 1
# Tool caches stay inside backend/ so no new top-level entry appears (DG-LAY-01).
export RUFF_CACHE_DIR := $(CURDIR)/backend/.ruff_cache
export MYPY_CACHE_DIR := $(CURDIR)/backend/.mypy_cache
_RUN_TMP := $(shell mkdir -p $(CURDIR)/.run/tmp)

LOCK ?=
TESTS ?=
K ?=
SLOW ?=
FRONTEND ?=
DB ?= dev
MSG ?=
CHECK ?=
ITEM ?=
FAMILY ?=
ID ?=
REQ ?=
# REL-COV-1 (DG-AK-42 rev 1.43): a filtered answer-keys run is the named diagnostic `answer-keys-filtered`;
# the wrapper's gate name follows the same condition the writer applies (any selection variable non-empty).
# AK_SCOPE=full is the ONE canonical G4 release run (DG-MK-answer-keys (5); Codex 1510): it clears any
# inherited FAMILY / ID / REQ explicitly (the cleared names go to the writer as EREV_AK_CLEARED), exports
# EREV_AK_SCOPE=full and EREV_AK_PLATFORM=db, and always names the canonical gate.
AK_SCOPE ?=
AK_FULL := $(filter full,$(AK_SCOPE))
$(if $(AK_SCOPE),$(if $(AK_FULL),,$(error AK_SCOPE must be 'full' (got '$(AK_SCOPE)'); DG-MK-answer-keys (5))))
AK_CLEARED := $(strip $(if $(FAMILY),FAMILY) $(if $(ID),ID) $(if $(REQ),REQ))
AK_TARGET := $(if $(AK_FULL),answer-keys,$(if $(strip $(FAMILY)$(ID)$(REQ)),answer-keys-filtered,answer-keys))
AK_SELECTION := $(if $(AK_FULL),EREV_AK_SCOPE=full EREV_AK_PLATFORM=db EREV_AK_CLEARED="$(AK_CLEARED)" FAMILY="" ID="" REQ="",FAMILY="$(FAMILY)" ID="$(ID)" REQ="$(REQ)")
TENANTS ?= all
RESET ?=
SPEC ?=
PROJECT ?=
BACKUP ?=
DRILL_PORT ?=
STRICT ?=
NO_CACHE ?=
EMBEDDED ?=
# REL-01 validation_level (DG-MK-release-manifest step 7): the author's declaration; absent = undeclared.
# Passed as DATA through the environment, never interpolated into a recipe's shell line — the release-manifest
# --command text is built from the known flags, not from MAKEOVERRIDES: the generator reads the value
# byte-exactly and validates it whole before any write (P1-VL-S1, P1-VL-S2).
VALIDATION_LEVEL ?=
export VALIDATION_LEVEL
# The AUTHORED BYTES are the declaration (P1-VL-S3): Make expands a command-line variable when exporting it
# ('MIN$(P1_UNSET)OR' arrives as MINOR), so the simply-expanded $(value) capture carries the unexpanded text
# and the generator reads it first.
export EREV_VALIDATION_LEVEL_RAW := $(value VALIDATION_LEVEL)
# GATE-BIND-1 (DG-MK-00i): the inner make a gate wrapper runs. A plain variable, never $(MAKE): GNU make
# executes recipe lines that contain $(MAKE) even under -n, and a dry run must not clone a context.
# Tests stub it with GATE_MAKE=true.
GATE_MAKE ?= make
RUN_DIR ?= $(CURDIR)/.run
ALEMBIC_INI := backend/alembic.ini

RUFF_CONFIG := --config backend/pyproject.toml
# frontend/config holds the Vite and ESLint configuration's helpers and tests; `make lint` did not
# reach it until two errors of config/vite.test.ts had stood unseen (dev-guide rev 1.209).
FRONTEND_LINT_PATHS := frontend/src frontend/config $(wildcard frontend/e2e)
# The tokens copy is a byte copy (DG-MK-tokens) that prettier must never rewrite.
PRETTIER_IGNORE := --ignore-path .gitignore --ignore-path frontend/.prettierignore
COMMA := ,
# DG-MK-build imports the worker whenever it exists (ruling D-78).
BUILD_IMPORTS := erev_api.cli, erev_api.main, erev_engine$(if $(wildcard backend/erev_api/worker.py),$(COMMA) erev_api.worker)
# EREV_API_PORT and EREV_WEB_PORT override the ports in supervisor review worktrees (D-70): from the
# environment, else from the .env file named by EREV_DOTENV, else the defaults (rulings D-78, D-80).
# Only a digits-only value of the named line is read, and nothing from the file is printed.
EREV_DOTENV ?= .env
dotenv_port = $(shell sed -n 's/^$(1)=\([0-9][0-9]*\)[[:space:]]*$$/\1/p' "$(EREV_DOTENV)" 2>/dev/null | tail -n 1)
API_PORT ?= $(or $(EREV_API_PORT),$(call dotenv_port,EREV_API_PORT),8190)
UVICORN_API := backend/.venv/bin/uvicorn erev_api.main:create_app --factory --host 127.0.0.1 --port $(API_PORT) --no-access-log
WEB_PORT ?= $(or $(EREV_WEB_PORT),$(call dotenv_port,EREV_WEB_PORT),5270)
# DG-RUN-03: the Vite dev server and its environment; Vite reads EREV_WEB_PORT (DG-RUN-21).
WEB_ENV := EREV_API_PROXY_TARGET=http://127.0.0.1:$(API_PORT) EREV_WEB_PORT=$(WEB_PORT) EREV_VITE_MODE=dev VITE_EREV_DESIGN_GALLERY=1
VITE_DEV := node frontend/node_modules/vite/bin/vite.js --config frontend/vite.config.ts
OPENAPI_DOCUMENT := docs/api/openapi.json
OPENAPI_SCHEMA := frontend/src/lib/api/schema.d.ts
PYTEST_PATHS := $(if $(TESTS),$(TESTS),backend/tests)
PYTEST_MARKERS := not parity and not answer_key and not perf$(if $(filter 1,$(SLOW)),, and not slow)
RUN_VITEST := $(if $(TESTS),,$(if $(filter 0,$(FRONTEND)),,1))
TEST_REPORTS := $(CURDIR)/.run/reports/test
# GATE-BIND-1 (DG-MK-00i): the ci gate's JUnit files live in the gate's own report directory so the
# wrapper copies them back from the execution context (make test alone keeps TEST_REPORTS).
CI_REPORTS ?= $(CURDIR)/.run/reports/ci

# $(call step,<command>,<reason>) runs one command and prints the DG-MK-00a failure line.
step = $(1) || { echo "FAIL $@: $(2)"; exit 1; }
# DG-MK-00b: every target except setup needs the installed environments.
REQUIRE_SETUP = { test -x $(PY) && test -d frontend/node_modules; } || { echo "FAIL $@: run make setup first"; exit 1; }

.PHONY: setup dev-up dev-down status backend frontend worker doctor migrate db-reset revision fixtures tokens registry-seed openapi fmt lint design-check vocab-check licence-check controls-report secrets-check typecheck test build ci test-pg properties answer-keys parity seed e2e release-manifest docker-build ci-gate test-pg-gate properties-gate parity-gate answer-keys-gate controls-report-gate e2e-gate tf-validate tf-validate-gate backup restore-verify backup-gate restore-verify-gate restore-drill restore-drill-gate audit-deps audit-deps-gate compose-verify compose-verify-gate zap-baseline zap-baseline-gate perf-seed perf perf-gate

setup:
	@LOCK="$(LOCK)" scripts/setup.sh

# DG-MK-dev-up: migrate dev, then api, worker and web by PID file (DG-RUN-01 to 03, DG-RUN-10).
# Running processes are reused.
dev-up:
	@$(REQUIRE_SETUP)
	@$(call step,$(MAKE) --no-print-directory migrate DB=dev,migrate)
	@$(call step,scripts/proc.sh start api $(API_PORT) -- $(UVICORN_API),api did not start; see .run/api.log)
	@$(call step,scripts/proc.sh start worker - -- $(EREV) worker,worker did not start; see .run/worker.log)
	@$(call step,$(WEB_ENV) scripts/proc.sh start web $(WEB_PORT) -- $(VITE_DEV),web did not start; see .run/web.log)
	@echo "API http://127.0.0.1:$(API_PORT)/api/v1"
	@echo "Web http://127.0.0.1:$(WEB_PORT)"
	@echo "OK dev-up"

# DG-MK-dev-down: stop web, worker and api by PID file (DG-RUN-11); e2e and compose processes stay.
dev-down:
	@$(REQUIRE_SETUP)
	@$(call step,scripts/proc.sh stop web,stop web)
	@$(call step,scripts/proc.sh stop worker,stop worker)
	@$(call step,scripts/proc.sh stop api,stop api)
	@echo "OK dev-down"

# DG-MK-status: name, PID, alive or stale, port and readiness of every .run/*.pid (DG-RUN-12).
status:
	@$(REQUIRE_SETUP)
	@$(call step,scripts/proc.sh status,proc.sh status)
	@echo "OK status"

# DG-MK-backend: foreground API (DG-RUN-01); refuses a port held by a process other than .run/api.pid.
backend:
	@$(REQUIRE_SETUP)
	@holder="$$(lsof -nP -iTCP:$(API_PORT) -sTCP:LISTEN -t 2>/dev/null | head -n 1)"; \
	if [[ -n "$$holder" && "$$holder" != "$$(cat "$(RUN_DIR)/api.pid" 2>/dev/null)" ]]; then \
		echo "FAIL $@: port $(API_PORT) in use by another process; not stopping it"; exit 1; \
	fi
	@$(call step,$(UVICORN_API)$(if $(filter 1,$(RELOAD)), --reload),uvicorn)
	@echo "OK backend"

# DG-MK-frontend: foreground Vite dev server on 5270 with the DG-RUN-03 environment; strictPort refuses a busy port.
frontend:
	@$(REQUIRE_SETUP)
	@$(call step,$(WEB_ENV) $(VITE_DEV),vite dev server)
	@echo "OK frontend"

# DG-MK-worker: foreground worker (DG-RUN-02) on all eight queues; never passes --queues (DG-KRN-JOB-11).
worker:
	@$(REQUIRE_SETUP)
	@$(call step,$(EREV) worker,erev worker)
	@echo "OK worker"

# DG-MK-doctor: the REQ-CTL-005 self-check against DB (dev, test or e2e); exit 1 on any failure.
doctor:
	@$(REQUIRE_SETUP)
	@case "$(DB)" in dev|test|e2e) ;; *) echo "FAIL $@: DB must be dev, test or e2e"; exit 1 ;; esac
	@$(call step,EREV_ENV=$(DB) $(EREV) doctor --db $(DB),a control-critical check failed; see the FAIL lines above)
	@echo "OK doctor"

# DG-MK-fixtures: copy and verify the legacy fixtures (DG-PAR-02); CHECK=1 verifies hashes and writes nothing.
fixtures:
	@$(REQUIRE_SETUP)
	@$(call step,$(PY) scripts/build_fixtures.py$(if $(filter 1,$(CHECK)), --check),$(if $(filter 1,$(CHECK)),legacy fixtures differ from the manifest,legacy fixture build))
	@echo "OK fixtures"

# DG-MK-tokens: byte copy of the normative tokens into the web app (DS-COL-00; checked by DS-LINT-14).
tokens:
	@$(REQUIRE_SETUP)
	@$(call step,cp docs/design/tokens.css frontend/src/styles/tokens.css,copy tokens.css)
	@echo "OK tokens"

# DG-MK-openapi: the committed OpenAPI 3.1 document and the generated TypeScript types.
openapi:
	@$(REQUIRE_SETUP)
	@$(call step,$(EREV) openapi --out $(OPENAPI_DOCUMENT),erev openapi)
	@$(call step,$(NODE_BIN)/openapi-typescript $(OPENAPI_DOCUMENT) -o $(OPENAPI_SCHEMA),openapi-typescript)
	@$(call step,$(NODE_BIN)/prettier --config frontend/.prettierrc --write $(OPENAPI_SCHEMA),prettier)
	@echo "OK openapi"

# DG-MK-migrate: upgrade head as erev_owner, then the DB-14 lint as erev_app. Never downgrades.
migrate:
	@$(REQUIRE_SETUP)
	@case "$(DB)" in dev|test|e2e) ;; *) echo "FAIL $@: DB must be dev, test or e2e"; exit 1 ;; esac
	@$(call step,EREV_ENV=$(DB) $(ALEMBIC) -c $(ALEMBIC_INI) upgrade head,alembic upgrade head)
	@$(call step,EREV_ENV=$(DB) $(EREV) db lint,catalogue lint)
	@echo "OK migrate"

# DG-MK-db-reset: an empty, migrated development database - the one the environment names: `erev`,
# or a lane's or a review's `erev_rv_*` in which no tenant lacks the demo marker (DG-ENV-13) -; never
# under a running dev stack.
db-reset:
	@$(REQUIRE_SETUP)
	@for name in api worker; do \
		pid="$$(cat "$(RUN_DIR)/$$name.pid" 2>/dev/null || true)"; \
		if [[ "$$pid" =~ ^[0-9]+$$ ]] && kill -0 "$$pid" 2>/dev/null; then \
			echo "FAIL $@: dev stack running; run make dev-down first"; exit 1; \
		fi; \
	done
	@$(call step,EREV_ENV=dev $(EREV) db reset,erev db reset)
	@$(call step,$(MAKE) --no-print-directory migrate DB=dev,migrate)
	@echo "OK db-reset"

# DG-MK-seed (WEB-10): the demo tenants WLD-T-00 to WLD-T-07 as the persona users, in dev. The password
# comes from the environment or the .env file named by EREV_DOTENV and is never printed; RESET=1 first
# runs db-reset. TENANTS=all (default) or comma-separated tenant codes. CLOSE=1 adds --with-close
# (CLO-22): the months the demo world shows as closed are closed through close runs, which takes
# minutes; without it every period of 2026 stays open, as the e2e stack and the tests seed it.
seed:
	@$(REQUIRE_SETUP)
	@{ test -n "$${EREV_DEMO_PASSWORD:-}" || grep -q '^EREV_DEMO_PASSWORD=.' "$(EREV_DOTENV)" 2>/dev/null; } || { echo "FAIL $@: EREV_DEMO_PASSWORD is not set. Copy it from .env.example."; exit 1; }
	@$(if $(filter 1,$(RESET)),$(call step,$(MAKE) --no-print-directory db-reset,db-reset),true)
	@$(call step,EREV_ENV=dev $(EREV) seed demo --tenants "$(TENANTS)"$(if $(filter 1,$(CLOSE)), --with-close),erev seed demo)
	@echo "OK seed"

# DG-MK-perf-seed (PRF-2): the volume tenant make perf measures, in the governed order. (1) password
# check, (2) `make migrate DB=dev`, (3) `erev perf seed` (idempotent: "perf-volume up to date" exits 0;
# another generator version exits 2 -> run make db-reset first; the same version incomplete resumes),
# (4) ANALYZE of the four hot tables as erev_owner (05 PERF-27), (5) `erev perf seed --snapshot-only`
# takes the stored snapshot (STORED_BACKUP) as of a known_at after the month-23 lock (D-98 148 A5, Q6 ruling:
# ANALYZE before the snapshot), (6) the seed writes .run/reports/perf-seed/report.json. Binds no port.
perf-seed:
	@$(REQUIRE_SETUP)
	@{ test -n "$${EREV_DEMO_PASSWORD:-}" || grep -q '^EREV_DEMO_PASSWORD=.' "$(EREV_DOTENV)" 2>/dev/null; } || { echo "FAIL $@: EREV_DEMO_PASSWORD is not set. Copy it from .env.example."; exit 1; }
	@$(call step,$(MAKE) --no-print-directory migrate DB=dev,migrate DB=dev)
	@$(call step,EREV_ENV=dev $(EREV) perf seed,erev perf seed)
	@$(call step,EREV_ENV=dev $(EREV) doctor --analyze schedule_line$(COMMA)subledger_line$(COMMA)contract_event$(COMMA)obligation_version,erev doctor --analyze)
	@$(call step,EREV_ENV=dev $(EREV) perf seed --snapshot-only,erev perf seed --snapshot-only)
	@echo "OK perf-seed"

# DG-MK-e2e (WEB-11): scripts/e2e.sh owns every step (password check, e2e-ports lock, database reset
# and seed, gallery build, the e2e stack by PID file, the Playwright projects and the report); SPEC and
# PROJECT pass through (DG-E2E-04).
# GATE-BIND-1 (DG-MK-00i): e2e runs in the execution context; PID files, logs and the ports lock
# stay in the worktree's run directory (EREV_RUN_DIR), the report is written in the context
# (EREV_REPORTS_DIR) and copied back to .run/reports/e2e/.
e2e:
	@$(REQUIRE_SETUP)
	@EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh e2e -- $(GATE_MAKE) --no-print-directory e2e-gate $(MAKEOVERRIDES)

e2e-gate:
	@$(REQUIRE_SETUP)
	@SPEC="$(SPEC)" PROJECT="$(PROJECT)" EREV_REPORTS_DIR="$(CURDIR)/.run/reports" EREV_E2E_COMMAND="$(strip make e2e $(MAKEOVERRIDES))" scripts/e2e.sh || { echo "FAIL e2e: scripts/e2e.sh failed; see the lines above and .run/reports/e2e/report.json"; exit 1; }
	@echo "OK e2e"

# DG-MK-perf (PRF-3, G9): the ports lock, the perf harness and the report are owned by scripts/perf.sh;
# every run targets the dev database `erev` (05 PERF-11) and is Ray-side. GATE-BIND-1 wraps it like e2e.
perf:
	@$(REQUIRE_SETUP)
	@EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh perf -- $(GATE_MAKE) --no-print-directory perf-gate $(MAKEOVERRIDES)

perf-gate:
	@$(REQUIRE_SETUP)
	@EREV_REPORTS_DIR="$(CURDIR)/.run/reports" EREV_PERF_COMMAND="$(strip make perf $(MAKEOVERRIDES))" scripts/perf.sh || { echo "FAIL perf: scripts/perf.sh failed; see the lines above and .run/reports/perf/report.json"; exit 1; }
	@echo "OK perf"

# DG-MK-revision: render the next handwritten revision (autogenerate is never used, DG-MIG-02).
revision:
	@$(REQUIRE_SETUP)
	@{ test -n "$(MSG)" && test -n "$(ITEM)"; } || { echo "FAIL $@: MSG and ITEM are required"; exit 1; }
	@$(call step,$(EREV) db revision --msg "$(MSG)" --item "$(ITEM)",erev db revision)
	@echo "OK revision"

# DG-MK-registry-seed: generate erev_api/registry/policies.py; CHECK=1 exits 1 when it is stale.
registry-seed:
	@$(REQUIRE_SETUP)
	@$(call step,$(EREV) registry-seed$(if $(filter 1,$(CHECK)), --check),$(if $(filter 1,$(CHECK)),policies.py is stale; run make registry-seed,erev registry-seed))
	@echo "OK registry-seed"

fmt:
	@$(REQUIRE_SETUP)
	@$(call step,$(RUFF) format $(RUFF_CONFIG) backend scripts,ruff format)
	@$(call step,$(RUFF) check $(RUFF_CONFIG) --fix --select I backend scripts,ruff import order)
	@$(call step,$(NODE_BIN)/prettier $(PRETTIER_IGNORE) --write $(FRONTEND_LINT_PATHS),prettier)
	@echo "OK fmt"

lint:
	@$(REQUIRE_SETUP)
	@$(call step,$(RUFF) format --check $(RUFF_CONFIG) backend scripts,ruff format --check)
	@$(call step,$(RUFF) check $(RUFF_CONFIG) backend scripts,ruff check)
	@$(call step,$(NODE_BIN)/prettier $(PRETTIER_IGNORE) --check $(FRONTEND_LINT_PATHS),prettier --check)
	@$(call step,$(NODE_BIN)/eslint --config frontend/eslint.config.js --max-warnings 0 $(FRONTEND_LINT_PATHS),eslint)
	@$(call step,$(MAKE) --no-print-directory design-check,design-check)
	@$(call step,$(MAKE) --no-print-directory vocab-check,vocab-check)
	@$(call step,$(MAKE) --no-print-directory licence-check,licence-check)
	@$(call step,$(MAKE) --no-print-directory secrets-check,secrets-check)
	@$(call step,scripts/openapi_check.sh,openapi document is stale; run make openapi)
	@$(call step,$(MAKE) --no-print-directory registry-seed CHECK=1,registry-seed check)
	@$(call step,$(MAKE) --no-print-directory fixtures CHECK=1,legacy fixtures check)
	@$(call step,$(EREV) controls-report --tags-only,control markers invalid; run erev controls-report --tags-only)
	@$(call step,test "$$($(ALEMBIC) -c $(ALEMBIC_INI) heads | grep -c .)" = 1,alembic heads must print exactly one head)
	@echo "OK lint"

# G7 (DG-MK-controls-report): exits 1 until every 1.0 control has a passing tagged test (BS-D-18).
# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/controls-report/.
controls-report:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh controls-report -- $(GATE_MAKE) --no-print-directory controls-report-gate $(MAKEOVERRIDES)

controls-report-gate:
	@$(REQUIRE_SETUP)
	@$(call step,$(EREV) controls-report --command "$(strip make controls-report $(MAKEOVERRIDES))",a 1.0 control lacks a passing tagged test; see .run/reports/controls-report/report.md)
	@echo "OK controls-report"

# DG-MK-design-check: the DS-LINT-21 self-test, then the DS-LINT scan of frontend/src (D-62).
design-check:
	@$(REQUIRE_SETUP)
	@$(call step,$(PY) scripts/design_check.py --config scripts/design_check.toml,design lint findings)
	@echo "OK design-check"

# DG-MK-vocab-check: the REQ-UX-010 term list over frontend/src and erev_api string constants (D-02).
vocab-check:
	@$(REQUIRE_SETUP)
	@$(call step,$(PY) scripts/vocab_check.py,forbidden vocabulary)
	@echo "OK vocab-check"

# DG-MK-licence-check: runtime Python and production npm licences against REQ-SEC-010, offline.
licence-check:
	@$(REQUIRE_SETUP)
	@$(call step,$(PY) scripts/licence_check.py,dependency licence outside the REQ-SEC-010 allow-list)
	@echo "OK licence-check"

secrets-check:
	@$(REQUIRE_SETUP)
	@$(call step,$(PY) scripts/secrets_check.py,secrets scan)
	@echo "OK secrets-check"

typecheck:
	@$(REQUIRE_SETUP)
	@$(call step,$(MYPY) --config-file backend/pyproject.toml --strict backend/erev_engine backend/erev_api,mypy)
	@$(call step,$(NODE_BIN)/tsc -b frontend,tsc)
	@echo "OK typecheck"

test:
	@$(REQUIRE_SETUP)
	@$(call step,EREV_ENV=test HYPOTHESIS_PROFILE=ci $(PYTEST) $(PYTEST_PATHS) -m "$(PYTEST_MARKERS)" $(if $(K),-k "$(K)") --basetemp=$(CURDIR)/.run/pytest --junitxml=$(TEST_REPORTS)/backend-junit.xml,backend tests)
	@$(if $(RUN_VITEST),$(call step,npm --prefix frontend run test -- --run --reporter=default --reporter=junit --outputFile.junit=$(TEST_REPORTS)/vitest-junit.xml,vitest),true)
	@echo "OK test"

build:
	@$(REQUIRE_SETUP)
	@$(call step,env -u VITE_EREV_DESIGN_GALLERY npm --prefix frontend run build,frontend build)
	@$(call step,$(PY) -c "import $(BUILD_IMPORTS)",backend imports)
	@echo "OK build"

# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/ci/.
ci:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh ci -- $(GATE_MAKE) --no-print-directory ci-gate $(MAKEOVERRIDES)

ci-gate:
	@$(REQUIRE_SETUP)
	@$(PY) scripts/gate_report.py ci --command "$(strip make ci $(MAKEOVERRIDES))" \
		--refuse "TESTS=$(TESTS)" --refuse "K=$(K)" --refuse "FRONTEND=$(FRONTEND)" \
		--refuse "OVERRIDES=$(strip $(MAKEOVERRIDES))" \
		--stage "env=$(PY) scripts/check_env.py --names --db" \
		--stage "lint=$(MAKE) --no-print-directory lint" \
		--stage "typecheck=$(MAKE) --no-print-directory typecheck" \
		--stage "test=$(MAKE) --no-print-directory test SLOW=1 TEST_REPORTS=$(CI_REPORTS)" \
		--stage "build=$(MAKE) --no-print-directory build" \
		--junit "backend=$(CI_REPORTS)/backend-junit.xml" \
		--junit "vitest=$(CI_REPORTS)/vitest-junit.xml"

# G6 (DG-MK-test-pg): the pg suite as erev_app on erev_test; the session fixture serialises runs.
# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/test-pg/.
test-pg:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh test-pg -- $(GATE_MAKE) --no-print-directory test-pg-gate $(MAKEOVERRIDES)

test-pg-gate:
	@$(REQUIRE_SETUP)
	@$(PY) scripts/gate_report.py test-pg --command "$(strip make test-pg $(MAKEOVERRIDES))" \
		--stage "pg=EREV_ENV=test HYPOTHESIS_PROFILE=ci $(PYTEST) backend/tests -m pg $(if $(K),-k '$(K)') --basetemp=$(CURDIR)/.run/pytest-pg --junitxml=.run/reports/test-pg/backend-junit.xml" \
		--junit "backend=.run/reports/test-pg/backend-junit.xml" \
		--fail-on-skipped backend

# G5 (DG-MK-properties): the Hypothesis invariants under the thorough profile (DG-PROP-01).
# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/properties/.
properties:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh properties -- $(GATE_MAKE) --no-print-directory properties-gate $(MAKEOVERRIDES)

properties-gate:
	@$(REQUIRE_SETUP)
	@$(PY) scripts/gate_report.py properties --command "$(strip make properties $(MAKEOVERRIDES))" \
		--stage "properties=EREV_ENV=test HYPOTHESIS_PROFILE=thorough $(PYTEST) backend/tests/properties -m property $(if $(K),-k '$(K)') --basetemp=$(CURDIR)/.run/pytest-properties --junitxml=.run/reports/properties/backend-junit.xml" \
		--counts-junit ".run/reports/properties/backend-junit.xml" \
		--fail-on-skipped properties

# G4 (DG-MK-answer-keys): validate every key, run the selected keys, check coverage when unfiltered.
# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/$(AK_TARGET)/ — the canonical answer-keys report
# for an unfiltered run, the named diagnostic answer-keys-filtered otherwise (REL-COV-1).
answer-keys:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh $(AK_TARGET) -- $(GATE_MAKE) --no-print-directory answer-keys-gate $(MAKEOVERRIDES)

answer-keys-gate:
	@$(REQUIRE_SETUP)
	@EREV_ENV=test PYTHONPATH=backend/tests$(if $(PYTHONPATH),:$(PYTHONPATH)) $(AK_SELECTION) \
		$(PY) -m support.answer_keys.report --command "$(strip make answer-keys $(MAKEOVERRIDES))" \
		--basetemp $(CURDIR)/.run/pytest-answer-keys

# G3 (DG-MK-parity): verify the legacy fixtures, run the golden parity cases selected by K, and write
# the DG-PAR-08 report; exit 1 unless every selected case passes and none is skipped.
# GATE-BIND-1 (DG-MK-00i): the gate runs in an immutable execution context; its report gains
# source_binding and is copied back to .run/reports/parity/.
parity:
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh parity -- $(GATE_MAKE) --no-print-directory parity-gate $(MAKEOVERRIDES)

parity-gate:
	@$(REQUIRE_SETUP)
	@$(MAKE) --no-print-directory fixtures CHECK=1
	@EREV_ENV=test PYTHONPATH=backend/tests$(if $(PYTHONPATH),:$(PYTHONPATH)) K="$(K)" \
		$(PY) -m support.parity.report --command "$(strip make parity $(MAKEOVERRIDES))" \
		--basetemp $(CURDIR)/.run/pytest-parity

# DG-MK-release-manifest (05 REL-01, REL-02, REL-04; SOP-2): offline; reads the gate reports under
# .run/reports/ and never runs a gate; STRICT=1 fails unless every gate is PASS on a clean worktree.
release-manifest:
	@$(REQUIRE_SETUP)
	@$(PY) scripts/release_manifest.py --command "$(strip make release-manifest $(if $(filter 1,$(STRICT)),STRICT=1) $(if $(filter 1,$(EMBEDDED)),EMBEDDED=1))"$(if $(filter 1,$(STRICT)), --strict)$(if $(filter 1,$(EMBEDDED)), --embedded)

# DG-MK-docker-build (supervisor target, D-48a; 05 DPL-05): scripts/docker_build.sh writes the embedded
# (pre-build, no image ids) manifest under the run directory, so the api and worker images carry
# release-manifest.json (05 REL-03) and the repository root is left alone (rev 1.97, R-53 (4)), builds from one
# exported context, probes the images and writes the attestation; NO_CACHE=1 for fresh builds, STRICT=1 for a
# strict manifest step.
docker-build:
	@echo "SUPERVISOR TARGET docker-build (D-48a)"
	@$(REQUIRE_SETUP)
	@NO_CACHE="$(NO_CACHE)" STRICT="$(STRICT)" EREV_DOCKER_BUILD_COMMAND="$(strip make docker-build $(MAKEOVERRIDES))" scripts/docker_build.sh

# DG-MK-audit-deps (supervisor target, D-48a; 05 SAR-17, THR-24) under GATE-BIND-1 (DG-MK-00i): the
# dependency audit runs in the execution context (uv export --no-dev --frozen, pip-audit
# --strict --require-hashes, npm audit --omit=dev; the advisory databases are the network use); its
# report with the two captured outputs is copied back to .run/reports/audit-deps/ with source_binding.
audit-deps:
	@echo "SUPERVISOR TARGET audit-deps (D-48a)"
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh audit-deps -- $(GATE_MAKE) --no-print-directory audit-deps-gate $(MAKEOVERRIDES)

audit-deps-gate:
	@$(REQUIRE_SETUP)
	@test -x scripts/audit_deps.sh || { echo "FAIL audit-deps: scripts/audit_deps.sh is not in this tree (DEP-5)"; exit 1; }
	@EREV_AUDIT_DEPS_COMMAND="$(strip make audit-deps $(MAKEOVERRIDES))" scripts/audit_deps.sh

# DG-MK-compose-verify (supervisor target, D-48a; G11; D-47) under GATE-BIND-1 (DG-MK-00i): the compose
# verification (project erev-verify only: build, up, readyz within 180 s, CSP smoke, worker heartbeat,
# down -v) runs in the execution context; skipped-no-daemon without Docker; the report is copied back to
# .run/reports/compose-verify/ with source_binding.
compose-verify:
	@echo "SUPERVISOR TARGET compose-verify (D-48a)"
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh compose-verify -- $(GATE_MAKE) --no-print-directory compose-verify-gate $(MAKEOVERRIDES)

compose-verify-gate:
	@$(REQUIRE_SETUP)
	@test -x scripts/compose_verify.sh || { echo "FAIL compose-verify: scripts/compose_verify.sh is not in this tree (DEP-5)"; exit 1; }
	@EREV_COMPOSE_VERIFY_COMMAND="$(strip make compose-verify $(MAKEOVERRIDES))" scripts/compose_verify.sh

# DG-MK-zap-baseline (supervisor target, D-48a; 05 SAR-43) under GATE-BIND-1 (DG-MK-00i): the ZAP
# baseline scan against project erev-verify (brought up through scripts/compose_verify.sh's keep-up
# contract, torn down by this script) runs in the execution context; skipped-no-daemon without Docker;
# the report, zap.json and zap.html are copied back to .run/reports/zap-baseline/ with source_binding.
zap-baseline:
	@echo "SUPERVISOR TARGET zap-baseline (D-48a)"
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh zap-baseline -- $(GATE_MAKE) --no-print-directory zap-baseline-gate $(MAKEOVERRIDES)

zap-baseline-gate:
	@$(REQUIRE_SETUP)
	@test -x scripts/zap_baseline.sh || { echo "FAIL zap-baseline: scripts/zap_baseline.sh is not in this tree (DEP-5)"; exit 1; }
	@EREV_ZAP_BASELINE_COMMAND="$(strip make zap-baseline $(MAKEOVERRIDES))" scripts/zap_baseline.sh

# DG-MK-tf-validate (supervisor target, D-48a) under GATE-BIND-1 (DG-MK-00i): the validate-only
# Terraform check runs in the execution context; its report (written by scripts/tf_validate.sh,
# owned by the deploy lane) is copied back to .run/reports/tf-validate/ with source_binding.
tf-validate:
	@echo "SUPERVISOR TARGET tf-validate (D-48a)"
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh tf-validate -- $(GATE_MAKE) --no-print-directory tf-validate-gate $(MAKEOVERRIDES)

tf-validate-gate:
	@$(REQUIRE_SETUP)
	@test -x scripts/tf_validate.sh || { echo "FAIL tf-validate: scripts/tf_validate.sh is not in this tree (DEP-5)"; exit 1; }
	@EREV_TF_VALIDATE_COMMAND="$(strip make tf-validate $(MAKEOVERRIDES))" scripts/tf_validate.sh

# DG-MK-backup (supervisor target, D-48a; 05 OPR-15, OPR-17, SAR-31; RB-04, RB-05) under GATE-BIND-1
# (DG-MK-00i): the backup-time digests (erev verify --all-tenants), pg_dump -Fc as the backup role, the
# files tarball, the .env copy with mode 0600 and the SHA-256 manifest. The set is written to this
# worktree's .data/backups/ (EREV_BACKUP_DIR); the report comes back from the execution context to
# .run/reports/backup/ with source_binding. The database URL never leaves the environment and the script
# prints only file names. Rev 1.81: the deployment's live data stays in the worktree, so the recipe also
# exports the worktree (EREV_BACKUP_DATA_ROOT: a relative EREV_FILE_ROOT resolves against it, not against
# the context) and its run directory (EREV_RUN_DIR: the api and worker PID files of step 0).
backup:
	@echo "SUPERVISOR TARGET backup (D-48a)"
	@$(REQUIRE_SETUP)
	@EREV_BACKUP_DIR="$(CURDIR)/.data/backups" EREV_BACKUP_DATA_ROOT="$(CURDIR)" EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh backup -- $(GATE_MAKE) --no-print-directory backup-gate $(MAKEOVERRIDES)

backup-gate:
	@$(REQUIRE_SETUP)
	@EREV_BACKUP_COMMAND="$(strip make backup $(MAKEOVERRIDES))" scripts/backup.sh

# DG-MK-restore-verify (supervisor target, D-48a; 05 OPR-11 (3) and (4), OPR-12, OPR-16; RB-04, RB-06)
# under GATE-BIND-1 (DG-MK-00i): restore backup BACKUP (default latest, read from this worktree's
# .data/backups/) into the ISOLATED erev_rv_* database named by EREV_RESTORE_OWNER_URL,
# EREV_RESTORE_APP_URL and EREV_RESTORE_ADMIN_URL, migrate, verify it against the backup digests, run
# doctor and record RPO/RTO; RESET=1 empties a used target first. Never a production database. The
# report comes back from the execution context to .run/reports/restore-verify/ with source_binding.
# Rev 1.81: the recipe exports this worktree's run directory (EREV_RUN_DIR), so the restore directory
# .run/restore/<backup id>/ (the extracted files a cutover points at, and the run's logs) outlives the
# execution context.
restore-verify:
	@echo "SUPERVISOR TARGET restore-verify (D-48a)"
	@$(REQUIRE_SETUP)
	@EREV_BACKUP_DIR="$(CURDIR)/.data/backups" EREV_RUN_DIR="$(RUN_DIR)" scripts/gate_context.sh restore-verify -- $(GATE_MAKE) --no-print-directory restore-verify-gate $(MAKEOVERRIDES)

restore-verify-gate:
	@$(REQUIRE_SETUP)
	@BACKUP="$(BACKUP)" RESET="$(RESET)" EREV_RESTORE_COMMAND="$(strip make restore-verify $(MAKEOVERRIDES))" scripts/restore_verify.sh

# DG-MK-restore-drill (supervisor target, D-48a; 05 OPR-12; RB-06) under GATE-BIND-1 (DG-MK-00i): the
# NATIVE backup and restore procedure rehearsed as one command on a throwaway compose PostgreSQL
# (project erev-verify-drill on 127.0.0.1:5446; DRILL_PORT chooses another port): RB-11 roles, the demo
# seed (TENANTS narrows it), the backup script, down -v, a fresh server, the restore script, the row
# counts of the clone against the source, teardown. RESET=1 first removes what an interrupted drill
# left. Nothing of a deployment is read or written; the drill's directory lies inside the execution
# context. The report comes back to .run/reports/restore-drill/ with source_binding.
restore-drill:
	@echo "SUPERVISOR TARGET restore-drill (D-48a)"
	@$(REQUIRE_SETUP)
	@scripts/gate_context.sh restore-drill -- $(GATE_MAKE) --no-print-directory restore-drill-gate $(MAKEOVERRIDES)

restore-drill-gate:
	@$(REQUIRE_SETUP)
	@DRILL_PORT="$(DRILL_PORT)" RESET="$(RESET)" TENANTS="$(TENANTS)" EREV_RESTORE_DRILL_COMMAND="$(strip make restore-drill $(MAKEOVERRIDES))" scripts/restore_drill.sh
