# eRev Cloud runbook

Operational procedures with their commands and expected output (REQ-OPS-003; 05 §7.7 RB-01 to RB-16). It holds the process-control (RB-01), migration (RB-02), self-check (RB-03), backup and restore (RB-04), master-key (RB-05), restore-test (RB-06), job-monitoring (RB-07), chain-failure (RB-08), replay-mismatch (RB-09), incident (RB-10), owner-identity (RB-11), partition (RB-12), digest-bucket (RB-13), erasure (RB-14), adapter-credential (RB-15) and upgrade-validation (RB-16) entries, plus the operational behaviour of the platform's commands. Names, channels and cloud identifiers that are not yet decided are marked `<…>` and listed as unknown inputs in `.run/supervisor/prod/unknown-inputs.md` (UI-2, UI-3, UI-9, UI-10).

The limits of release 1.0 that bear on operations — performance at volume, which is not measured, an import left behind a failed commit job, and the hosted inputs that are not given — are stated in [the limits of release 1.0](../release/LIMITS-1.0.md), sections A, B.5 and B.8.

## Start and stop by PID files

Runbook entry RB-01 (dev-guide DG-RUN-10 to DG-RUN-12). Servers bind `127.0.0.1` only, on fixed ports, and each records its process id in `.run/`.

| Process | Port | PID file | Log | Ready when |
|---|---|---|---|---|
| `api` | 8190 | `.run/api.pid` | `.run/api.log` | `GET http://127.0.0.1:8190/api/v1/readyz` returns 200 |
| `worker` | none | `.run/worker.pid` | `.run/worker.log` | `.run/worker.heartbeat` modified within 60 s |
| `web` | 5270 | `.run/web.pid` | `.run/web.log` | `GET http://127.0.0.1:5270/` returns 200 |

### Development stack

```sh
make dev-up
make status
make dev-down
```

- `make dev-up` applies the migrations to the dev database (`make migrate DB=dev`), starts `api`, `worker` and `web` with `scripts/proc.sh start` as below, and prints `API http://127.0.0.1:8190/api/v1` and `Web http://127.0.0.1:5270` before `OK dev-up`. A process already running from its PID file is reused, not restarted.
- `make status` prints `scripts/proc.sh status` (see "Status") and ends with `OK status`.
- `make dev-down` stops `web`, then `worker`, then `api` by PID file and ends with `OK dev-down`. It never touches the e2e processes.

### Probe the port

```sh
lsof -nP -iTCP:8190 -sTCP:LISTEN
```

No output means the port is free. A listener that no `.run/*.pid` file names belongs to someone else: leave it running and do not start a second server.

### Start

```sh
scripts/proc.sh start api 8190 -- backend/.venv/bin/uvicorn erev_api.main:create_app --factory --host 127.0.0.1 --port 8190 --no-access-log
scripts/proc.sh start web 5270 -- env EREV_API_PROXY_TARGET=http://127.0.0.1:8190 EREV_VITE_MODE=dev VITE_EREV_DESIGN_GALLERY=1 node frontend/node_modules/vite/bin/vite.js --config frontend/vite.config.ts
```

The command runs the server binary directly, so the recorded PID is the server itself (DG-RUN-13).

| Situation | Output | Exit |
|---|---|---|
| Started and ready within 60 s | `api started (pid <n>)` | 0 |
| Already running from its PID file | `api already running (pid <n>)` | 0 |
| Port held by a process no PID file names | `port 8190 in use by another process; not stopping it` | 1 |
| Not ready within 60 s | `api not ready within 60 s; last 40 lines of .run/api.log:` followed by the log lines | 1 |

For foreground work use `make backend` (the api; `RELOAD=1` adds auto-reload in the foreground only) or `make frontend` (the web dev server). Background servers never auto-reload (DG-RUN-14).

### Status

```sh
scripts/proc.sh status
```

Each PID file prints one line, for example `api pid=4242 alive port=8190 ready=ready`. A dead process prints `stale` with `ready=-`, and its PID file is kept for inspection. With no PID files the output is `no processes recorded in .run/`.

### Ports in a review worktree

A supervisor review worktree runs its own stack beside the main checkout, so its `.env` names other ports (01-DECISIONS D-70, D-80), for example:

```dotenv
EREV_API_PORT=8192
EREV_WEB_PORT=5272
EREV_E2E_API_PORT=8198
EREV_E2E_WEB_PORT=5278
```

- `make` and `scripts/proc.sh` take each port from the environment first, then from the `.env` file named by `EREV_DOTENV` (default `.env`, relative to the repository root), then from the defaults 8190, 5270, 8199 and 5279. Only a line of the form `NAME=<digits>` counts; no value from the file is printed.
- `make dev-up` then starts `proc.sh start api 8192` and `proc.sh start web 5272`, and passes `EREV_WEB_PORT=5272` to Vite, which binds it with `strictPort` (DG-RUN-21). `make -n dev-up` shows the resolved ports without starting anything.
- `make backend` and `make frontend` use the same ports; `make dev-up API_PORT=8192 WEB_PORT=5272` overrides both for one run.
- `scripts/proc.sh status` reports the resolved port of each PID file. `EREV_RUN_DIR` in the environment moves the PID directory away from `.run/`.

### Stop

```sh
scripts/proc.sh stop web
scripts/proc.sh stop api
```

| Situation | Output | Exit |
|---|---|---|
| Running | TERM, up to 15 s of waiting, then KILL; `api stopped (pid <n>)` | 0 |
| No PID file | `api not running` | 0 |
| PID file of a dead process | `api not running (stale pid file removed)` | 0 |

Stop only by PID file. Never use `pkill`, `killall` or `kill $(lsof …)`, and never stop a process you did not start (DG-FORBID-02, DG-RUN-15).

## Compose stack: start, first operator and first workspace

The compose file runs the release images in `production` mode behind nginx on `http://127.0.0.1:8195` (05 DPL-10 to DPL-16): `postgres`, the one-shot `migrate` job, `api`, `worker` and `web`. The api and worker images hold no shell and no checkout, so every command this runbook writes as `backend/.venv/bin/erev …` for a repository checkout runs there as `/app/.venv/bin/erev …` inside a container, under the container's own `EREV_ENV` (`production`): an `EREV_ENV=…` prefix on the host line selects nothing in a container, and the checkout form would reach the database of the checkout's `.env`, not the stack. Each step below was run against project `erev-verify` (record `docs/reviews/loop/sprint/OPS.md`).

### The environment file

`deploy/compose.env.example` holds placeholders and no master key, so it starts nothing as it is: the database's first start refuses the `change-me-…` passwords and the container stays unhealthy, so nothing that depends on it is started; with passwords alone, `migrate` stops with `EREV_ENCRYPTION_KEY must be set when EREV_KEY_PROVIDER is local`. Copy it, keep the copy out of version control (for a deployment, outside the repository) and set:

| Variables | What to set |
|---|---|
| `EREV_COMPOSE_POSTGRES_PASSWORD`, `EREV_COMPOSE_OWNER_PASSWORD`, `EREV_COMPOSE_APP_PASSWORD` | Three passwords of at least 12 URL-safe characters (letters, digits, `-`, `_`), each from `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`. They are set when the database volume is first created, and that first start refuses a password that is missing, shorter than 12 characters or still one of the example's `change-me-…` placeholders: the `postgres` log ends with `EREV_COMPOSE_POSTGRES_PASSWORD, EREV_COMPOSE_OWNER_PASSWORD and EREV_COMPOSE_APP_PASSWORD must not be the change-me placeholders of deploy/compose.env.example: generate each one, remove the database volume and start again`, the container restarts, and its server holds no application role and no `erev` database. The health check signs in as `erev_app` on `erev` and cannot: after about two and a half minutes the container is `unhealthy`, `docker compose … up -d` ends with `dependency failed to start: container <project>-postgres-1 is unhealthy`, and `migrate`, the api, the worker and the web are not started. A database of another name, or a volume another setup created, ends the same way; `docker inspect <project>-postgres-1` shows the check's last answer, for example `role "erev_app" does not exist`. Correct the file, remove the volume (`docker compose … down -v`) and start again |
| `EREV_COMPOSE_ENCRYPTION_KEY`, `EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY`, `EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY` | Three different keys, each from `python3 -c "import secrets; print(secrets.token_hex(32))"`. Under `production` the api and the worker refuse to start on a placeholder (a key with fewer than 16 distinct byte values) and on two equal keys. Keep them with the backups and never change them on a live deployment: data encrypted and chains signed under them cannot be read or verified without them ("Master-key backup and key rotation") |
| `EREV_COMPOSE_PUBLIC_ORIGIN` | The origin users reach, without a path: `http://127.0.0.1:8195` for this stack, the `https://` origin of a deployment served over TLS ("Serving over HTTPS") |
| `EREV_COMPOSE_SMTP_HOST`, `EREV_COMPOSE_SMTP_PORT`, `EREV_COMPOSE_SMTP_USERNAME`, `EREV_COMPOSE_SMTP_PASSWORD`, `EREV_COMPOSE_SMTP_FROM` | The SMTP relay and the sender address. `production` refuses the fake email backend. The relay must offer STARTTLS, present a certificate valid for its host name and resolve to public addresses only ("Outbox and email"). Leave the user name and password blank for a relay without authentication. The example names a host that never resolves: a stack that keeps it starts and sends no mail |
| `EREV_COMPOSE_SMTP_PRIVATE_RELAY`, `EREV_COMPOSE_SMTP_CA_FILE` | Only for a relay on a private or loopback address, such as one on the stack's own network: `true`, and the path inside the api and worker containers of the PEM file with the certificate authority that signed the relay's certificate ("A relay on the stack's own network"). Leave `false` and blank otherwise |

For a local stack the keys and the database passwords can be generated into a copy under the git-ignored run directory:

```sh
umask 077
cp deploy/compose.env.example .run/compose.env
for name in EREV_COMPOSE_ENCRYPTION_KEY EREV_COMPOSE_AUDIT_HMAC_MASTER_KEY EREV_COMPOSE_SECURITY_EVENT_HMAC_KEY; do
  sed -i.bak "s/^$name=.*/$name=$(python3 -c 'import secrets; print(secrets.token_hex(32))')/" .run/compose.env
done
for name in EREV_COMPOSE_POSTGRES_PASSWORD EREV_COMPOSE_OWNER_PASSWORD EREV_COMPOSE_APP_PASSWORD; do
  sed -i.bak "s/^$name=.*/$name=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')/" .run/compose.env
done
rm -f .run/compose.env.bak
```

### Start

```sh
make release-manifest EMBEDDED=1      # the manifest the api and worker images copy (05 REL-03)
docker compose -f deploy/compose.yaml --env-file .run/compose.env -p erev-verify up -d --build
curl -s http://127.0.0.1:8195/api/v1/readyz
```

Expected: `migrate` exits 0 with `DB-14 lint: 0 findings` (a second run changes nothing), `api` and `worker` become `healthy`, and the last command prints `{"status":"ready","checks":{"database":"ok","migrations":"ok","files":"ok","keys":"ok"}}`. `make compose-verify` runs the same bring-up with the example file and the three keys and three database passwords it generates for the run, checks it and tears it down. `make release-manifest EMBEDDED=1` leaves `release-manifest.json` at the repository root (`make docker-build` does not: it keeps its manifest under the run directory; `make compose-verify` and `make zap-baseline` write theirs for the build and leave the root as it stood when they end); it describes that commit. Once the checkout moves to a commit with another schema revision, a development process started from it (`make seed`, `make backend`, the worker) refuses with `ReleaseManifestError: the release manifest names another schema revision` until the manifest is written again or removed. Stop the stack with `docker compose -f deploy/compose.yaml --env-file .run/compose.env -p erev-verify down`; adding `-v` also destroys the database and file volumes. After a changed variable or with a new image, `docker compose … up -d` recreates the `api` container, possibly on another address of the stack's network; `web` needs no restart, because nginx resolves the name `api` when it proxies a request and follows a new address within ten seconds. `up -d` also starts what a service depends on, so `docker compose … up -d worker` (or `api`) runs the one-shot `migrate` job again before it starts the service: at the same version the upgrade finds the schema at head and the lint is read-only, so the run changes nothing and exits 0; with a new image it applies that image's migrations first, which is the order an upgrade needs. To recreate one service and nothing else, add `--no-deps`: `docker compose … up -d --no-deps worker`.

A production api or worker that is handed the fake email backend, `smtp` without a relay or a sender, a placeholder key or two equal keys does not start: the api exits 3 and the worker 1 before either opens a database connection, and the log event `startup.refused` lists the findings, for example `FAIL email-backend: EREV_EMAIL_BACKEND is fake; production requires smtp (05 CFG-17, SAR-40)` or `FAIL master-keys: EREV_ENCRYPTION_KEY is a placeholder, not a generated key: fewer than 16 distinct byte values (05 CFG-26)`. `docker compose … logs api` shows it; `web` then never starts, because it waits for a healthy api. The operator commands refuse the same configuration: `erev tenant create` and `tenant resend-invitation`, `operator create`, the `idp` commands, `support-grant request`, `restore-applied`, `seed demo` and `perf seed` print the `FAIL` lines and `production refuses to run this command with this configuration (05 SAR-40 startup subset); erev doctor lists every finding` on stderr and exit 3, before they ask for a password or open a connection, so no workspace is provisioned under placeholder keys. `erev doctor` and `erev verify` always run. `erev migrate` is not refused: it applies the schema and uses neither mail nor keys.

Every `erev` command writes its log lines as JSON on stderr (the `EREV_LOG_LEVEL` and `EREV_LOG_FORMAT` of the api and the worker, with the same scrubbing); stdout carries the command's own output only, for example `DB-14 lint: 0 findings` for `migrate`. `docker compose … logs migrate` shows both streams, Alembic's `Running upgrade` lines among the JSON.

The api and the worker connect as `erev_app` only. The `migrate` service alone holds the `erev_owner` URL, so the commands that need the owner run through it, each in a container that is removed afterwards: `docker compose … run --rm migrate migrate`, `… run --rm migrate idp create …` ("Identity providers (OIDC sign-in)") and `… run --rm migrate doctor --analyze <tables>`. Every other command runs in the api container (`docker compose … exec api /app/.venv/bin/erev …`). The worker needs what the api needs and nothing of the owner: the application URL, the three master keys (it encrypts and decrypts files and stored secrets, and signs and verifies the audit and security-event chains) and the SMTP variables (it sends the mail).

| Step | Command or route | Expected |
|---|---|---|
| 1. First operator | `docker compose -f deploy/compose.yaml --env-file .run/compose.env -p erev-verify exec api /app/.venv/bin/erev operator create --email <email> --name "<display name>"` | A hidden password prompt, twice; then one JSON line `{display_name, email, id, is_operator: true}` and exit 0. Without a terminal, send the password twice on standard input and add `-T` after `exec` (standard error then warns that the input may be echoed). |
| 2. Operator signs in and enrols TOTP | `POST /api/v1/session/login`, then `POST /api/v1/me/mfa/enroll` and `POST /api/v1/me/mfa/confirm` (see "Multi-factor authentication") | Sign-in answers 200 with `mfa_required` and `mfa_enrolment_required` both false for a new operator; `POST /api/v1/operator/tenants` answers 403 `mfa-required` until the factor is confirmed. |
| 3. First workspace | `POST /api/v1/operator/tenants` from that session, or `docker compose … exec api /app/.venv/bin/erev tenant create --code <code> --name "<display name>" --reporting-currency <ISO 4217> --admin <email>` (see "Tenant provisioning") | 201, or one JSON line and exit 0; a code in use answers 422 `TENANT_CODE_EXISTS`. |
| 4. Invitation email | The worker sends it through the SMTP relay within a minute of step 3. `docker compose … exec -T postgres psql -U postgres -d erev -c "select topic, status, attempt_count, last_error from erev.outbox_message order by created_at desc limit 3"` shows the message | `EMAIL` with status `DISPATCHED`, and the message in the administrator's mailbox ending with the link `<EREV_PUBLIC_ORIGIN>/accept-invitation#token=…`. With a relay that does not resolve, such as the example's, the row reads `FAILED` with `last_error` `DestinationRefused`, is retried after 30 s × 2^attempt and ends `DEAD` after the tenth failure: nothing is delivered, and steps 5 and 6 need a working relay. |
| 5. Tenant Admin accepts | Open the link in a browser | "You were invited as … to …"; a password of at least 12 characters; then "Set up multi-factor authentication" (QR code, code, ten recovery codes) and the workspace setup checklist at `/settings/setup`. |
| 6. Sign in again | `<EREV_PUBLIC_ORIGIN>/sign-in` | Password, then the TOTP challenge; without the challenge every administration route answers 403 `mfa-required`. |

The session cookie carries `HttpOnly` and `SameSite=Lax`, and `Secure` unless `EREV_PUBLIC_ORIGIN` is an `http` origin on a loopback host (`127.0.0.1`, `localhost`, `::1`): the attribute follows the configured origin, never the `Host` header of a request, and an `http` origin on any other host keeps `Secure` — a browser then returns no cookie and nobody can sign in, which is the sign of a wrong `EREV_COMPOSE_PUBLIC_ORIGIN`. This stack's origin is plain HTTP on `127.0.0.1`, so its cookie has no `Secure`, and `erev doctor` fails `session-cookie` for it by design (see "Production checks").

### A relay on the stack's own network

The example relay never resolves, so a stack that keeps it invites nobody. A relay that answers on a private or loopback address — a container on this stack's network, a host on the same private network — is refused by the public-address rule until the operator opts in (05 SAR-15, CFG-18):

1. In the environment file set `EREV_COMPOSE_SMTP_HOST` to the relay's name, `EREV_COMPOSE_SMTP_PORT` to its STARTTLS port, `EREV_COMPOSE_SMTP_FROM` to the sender and `EREV_COMPOSE_SMTP_PRIVATE_RELAY=true`.
2. The relay must still offer STARTTLS with a certificate valid for the name in `EREV_COMPOSE_SMTP_HOST`. When your own authority signed that certificate, mount the authority's certificate (PEM) read-only into the api and the worker, and name its path inside the containers in `EREV_COMPOSE_SMTP_CA_FILE`. An override file leaves `deploy/compose.yaml` untouched:

   ```yaml
   # relay.override.yaml: a relay on the stack's network and the authority that signed its certificate
   services:
     relay:
       image: <your relay image>   # STARTTLS on 587 with a certificate for the name "relay"
     api:
       volumes:
         - /path/to/relay-ca.pem:/etc/erev/smtp-ca.pem:ro   # an absolute path on the host
     worker:
       volumes:
         - /path/to/relay-ca.pem:/etc/erev/smtp-ca.pem:ro
   ```

   with `EREV_COMPOSE_SMTP_HOST=relay` and `EREV_COMPOSE_SMTP_CA_FILE=/etc/erev/smtp-ca.pem`, started as `docker compose -f deploy/compose.yaml -f relay.override.yaml --env-file .run/compose.env -p erev-verify up -d --build`. Both services read the file when they start; a path that is not mounted stops them with `FAIL email-backend: EREV_SMTP_CA_FILE is not a readable PEM bundle of certificate authorities (05 CFG-18)`.
3. `erev doctor` prints `WARN email-backend: EREV_SMTP_PRIVATE_RELAY is on: …` for as long as the opt-in is set. The warning does not fail the command.

The opt-in covers the SMTP relay only. Webhook endpoints, integration connections and identity providers keep the public-address rule, and the relay itself may still not be on a link-local address.

### Serving over HTTPS

Compose publishes plain HTTP on `127.0.0.1` only (03 REQ-SEC-001). To serve users, terminate TLS 1.2 or later and set `EREV_COMPOSE_PUBLIC_ORIGIN` to the `https://` origin, so that the session cookie is `Secure` and the links in email are right. `Strict-Transport-Security: max-age=31536000; includeSubDomains` must reach the browser from the tier that terminates TLS (05 SAR-20):

| Where TLS ends | What to do | Who sends `Strict-Transport-Security` |
|---|---|---|
| nginx of the web image | Enable the `8443` server documented at the end of `deploy/docker/nginx/default.conf` (mount the configuration, the certificate and the key read-only; publish 8443; repeat the locations of the plain server inside it, with the `set $erev_api http://api:8080;` line they pass to) | nginx, on every response of that server: `security-headers.conf` carries the header with a value that is empty on plain HTTP. Do not add it at server level — nginx drops inherited `add_header` lines in a location that sets its own, and every location does |
| A proxy or load balancer in front of the stack | Forward to `127.0.0.1:8195`; raise `EREV_TRUSTED_PROXY_HOPS` in `deploy/compose.yaml` by one for each proxy between the client and nginx | That proxy. nginx then speaks plain HTTP and sends none |
| Hosted (Terraform) | Nothing: the HTTPS load balancer terminates TLS | The load balancer, as a custom response header on every backend service (05 DPL-40) |

Hosted, the load balancer sends `/api` and `/api/*` to the api service and everything else to the web service (`deploy/terraform/gcp/load_balancer.tf`), whose ingress admits the load balancer alone. The `/api/` locations of the web image are therefore never reached there and need no setting: nothing on Cloud Run is named `api`, and the image starts without that name. A request that did reach one of them would be answered 502 after five seconds, because no resolver answers at `127.0.0.11` outside a compose network. Not verifiable without a deployment: at the first hosted rollout, confirm that the `erev-web` revision becomes ready and that `/api/v1/healthz` is answered by the api service.

Measured on the built web image with the documented `8443` server enabled (record `docs/reviews/loop/sprint/OPS.md`): every response over TLS carried the header once — the SPA, an asset, a missing asset's 404 and the proxied api routes — and no response of the plain-HTTP server carried it. The header is never sent over plain HTTP, where a browser ignores it, and never by the api.

## Migrations

Runbook entry RB-02 (dev-guide DG-MK-migrate, DG-MK-revision, DG-MK-db-reset; `docs/04-DATA_MODEL.md` §18).

### Apply

```sh
make migrate            # database erev (DB=dev)
make migrate DB=test    # erev_test; DB=e2e for erev_e2e
```

1. `alembic -c backend/alembic.ini upgrade head` runs as `erev_owner` on the selected database.
2. `erev db lint` runs as `erev_app` and exits 1 on any catalogue finding (DB-14).

The final line is `OK migrate`. A failure ends with `FAIL migrate: alembic upgrade head` or `FAIL migrate: catalogue lint`. The target never downgrades; downgrades run only inside the migration round-trip test on `erev_test` (DG-MIG-05).

### A revision that is cancelled

A migration's connection carries two limits (05 TXN-03): a statement may run for `EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS` seconds (1800 by default; 30 to 86400), and it waits at most 10 seconds for a lock. Each revision is one transaction, so a revision that is cancelled leaves nothing of itself: the database stands at the revision before it, the revisions applied earlier in the same run stay applied, and `make migrate` ends with `FAIL migrate: alembic upgrade head`.

- `canceling statement due to lock timeout` (SQLSTATE 55P03): another transaction held a table the revision changes. The 10 seconds are deliberate and are not raised: a schema change that waited would hold every later request on that table behind itself. Run the migration again when that transaction has ended; the run starts at the cancelled revision. No statement of a request runs longer than 30 or 60 seconds and no transaction idles longer than 60 (05 TXN-03), so a request's transaction is short; a job's lasts as long as its work and holds the tables it has read until it ends. `pg_stat_activity` shows the open transactions and since when (`xact_start`), and each connection of the application names its component in `application_name` (`erev-api`, `erev-worker`); a session from outside the application shows there too. Read it as a role that sees other roles' sessions — the instance's administrator, or a member of `pg_read_all_stats`; `erev_owner` sees only its own.
- `canceling statement due to statement timeout` (SQLSTATE 57014): one statement of the revision ran longer than the migration's limit. On a large table a foreign key or a check constraint is validated over every row in one statement. Run the migration again with the limit raised for that run: `EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS=<seconds> make migrate`; in a compose deployment `docker compose … run --rm -e EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS=<seconds> migrate migrate`; hosted, the job is executed with both raised for that execution alone — `gcloud run jobs execute erev-migrate --region <region> --update-env-vars EREV_MIGRATION_STATEMENT_TIMEOUT_SECONDS=<seconds> --task-timeout <seconds>s --wait` — and the job's definition (Terraform `migrate_timeout_seconds`, 1800 seconds by default) stays as it is. Hosted the task's limit is the one an operator meets first: a statement begins after its task, so with equal values Cloud Run ends the task before PostgreSQL cancels the statement; the revision's transaction is rolled back all the same and the database stands at the revision before it.

### Add a revision

```sh
make revision MSG="<summary>" ITEM=<BUILD_SPEC item id>
```

The target prints the path of the new handwritten revision under `backend/erev_api/db/migrations/versions/`. Autogenerate is never used. `make lint` fails unless `alembic heads` prints exactly one head.

### Reset the dev database

```sh
make db-reset
```

The target drops schema `erev` in the development database the environment names, as `erev_owner`, and migrates again, which removes every tenant. It refuses with `FAIL db-reset: dev stack running; run make dev-down first` while `.run/api.pid` or `.run/worker.pid` names a live process; stop those processes by PID file first. It never touches `erev_test` or `erev_e2e`. A development database is `erev` or an `erev_rv_*` database under `EREV_ENV=dev` in which every tenant carries the demo marker (a sandbox counts by its source); otherwise `erev db reset` says which of the three does not hold — for example `refusing to reset <database>: 1 tenant(s) carry no demo marker, so it is not a development database` — and drops nothing. The final line is `OK db-reset`.

Reseed after the LEGACY JET-15 side change (D-89 L7-6-Q-8; D-90): reseed any long-lived dev or QA tenant that enabled the `LEGACY` book before commit b1886ec, for example with `make seed RESET=1` on the dev database, because its LEGACY JET-15 lines were sealed under the old sides. No seeded tenant keeps a `LEGACY` book, and there is no data migration.

A demo seed runs every statement under the 60 seconds of a unit of work, planning included (05 TXN-03). On a server starved of CPU the first statement to meet that limit reads a partitioned table: `audit_event`, `schedule_line` and `subledger_line` hold 181 partitions each, one a month and a default, and a read without a bound on the partition key plans every one of them. The seed then stops with `canceling statement due to statement timeout` and leaves the tenant it was writing unfinished. Nothing is wrong with the data model; seed again from a reset (`make seed RESET=1`) when the server has CPU to give.

### Pre-migration backup

Every schema migration is preceded by a backup at the point the migration would roll back to (05 OPR-16).

```sh
make backup              # local and self-hosted: the five files of RB-04 under .data/backups/
make migrate
```

Hosted, the release pipeline takes an on-demand backup before the `erev-migrate` job runs:

```sh
gcloud sql backups create --instance=<production instance> --description="pre-migration <release tag>"
gcloud sql backups list --instance=<production instance> --limit=1
```

The backup id printed by the second command goes into the release record. A migration that fails, or a release that has to be withdrawn after its migration, is recovered by RB-04 "Restore into a clone": the clone is created at this backup, `erev migrate` runs forward on the clone under the release that is being validated, the clone is verified and cut over to. Nothing runs `alembic downgrade` outside the round-trip test (DG-MIG-08).

### Hosted deployments

- A one-shot migration job runs `alembic upgrade head` as `erev_owner` from the release image (05 CMP-09). The api and worker processes never migrate.
- Every hosted release with a schema migration takes an on-demand database backup before the job runs (05 OPR-16).
- Production is forward-fix only: no hosted database is ever downgraded (DG-MIG-08).
- A failed hosted migration is rolled back by restore through clone and cutover (05 OPR-11) at the pre-migration backup point (05 OPR-16). Declare an incident, create a point-in-time clone at the instant of that backup, run `erev doctor` and the chain verification against the clone, point the database URL secrets to the clone, and deploy a new revision. Production data is never restored in place.

## erev doctor

Runbook entry RB-03 (03 REQ-CTL-005; dev-guide DG-MK-doctor). `erev doctor` checks the control-critical configuration of one database and exits 1 when any check fails. A deployment that fails it is unsupported.

```sh
make doctor
make doctor DB=test
backend/.venv/bin/erev doctor --db e2e
```

`make doctor` checks the dev database; `DB=test` or `DB=e2e` selects another. `--db` takes `dev`, `test` or `e2e` and selects the database URLs as `EREV_ENV` does; without it the command checks the database of `EREV_ENV`. The command connects as `erev_app`, and reading the workspace list records one `PLATFORM_SCOPE_USED` security event. A healthy database prints one line per check:

```text
OK row-level-security: 32 tenant tables have forced row level security and a policy
OK app-role: erev_app has neither SUPERUSER nor BYPASSRLS
OK immutability-triggers: 627 triggers enabled; every IM-A table carries its DB-01 triggers
OK audit-chain: latest verification PASS for 3 of 3 tenants
OK ai: ai.enabled defaults to false; AI enabled for 0 of 3 tenants
OK setting-references: 41 functions reference only the documented app.* settings
OK doctor
```

A failing check prints one `FAIL <check>: <finding>` line per finding instead of its `OK` line, and `make doctor` ends with `FAIL doctor: a control-critical check failed; see the FAIL lines above`.

`erev doctor --analyze schedule_line,subledger_line,contract_event,obligation_version` runs `ANALYZE` on the named
schema-`erev` tables as `erev_owner` and runs no check (05 PERF-27; DG-MK-perf-seed step 4): planner statistics need the
table owner, so no application job runs them. It prints `OK analyze: 4 tables analyzed as erev_owner`; a name that is not
a schema-`erev` table exits 2 with `unknown table <name>`. Hosted deployments rely on autovacuum and the RB-12 procedure.

| Check | Fails when | Response |
|---|---|---|
| `row-level-security` | A table with `tenant_id` lacks ROW LEVEL SECURITY, FORCE or a policy, or `tenant` lacks forced row level security (04 DB-14 (a), (c)) | Tenant isolation is not enforced: stop the api and worker. `make migrate` runs the same lint; restore the missing statement with a forward-fix revision. |
| `app-role` | `erev_app` has SUPERUSER or BYPASSRLS (DB-14 (d)) | Row level security does not bind the role. The database administrator removes the attribute; no release fixes it. |
| `immutability-triggers` | A trigger in schema erev is disabled or fires only in replica sessions (the finding names the trigger), or an IM-A table or partition lacks its DB-01 trigger (DB-14 (g)) | Re-enable the trigger as `erev_owner` with `ALTER TABLE erev.<table> ENABLE TRIGGER <trigger>`. Rows could change while it was off, so handle it as a SEV-1 incident (05 RB-08): find the session that disabled it and start a chain verification. |
| `audit-chain` | The latest `audit_chain_verification` of a workspace is not `PASS` (the finding names the workspace code and the first failing sequence), or an ACTIVE workspace created more than 26 hours ago has no verification | For a `FAIL`, follow "Chain verification". For a missing verification, check that the worker runs, then start one with `POST /api/v1/audit-events/verify`. A workspace younger than 26 hours counts as awaiting its first verification. |
| `ai` | Registry parameter `ai.enabled` is missing or does not default to false, or a workspace's value does not resolve to a boolean | AI must stay off unless a workspace enables it. Compare `erev.registry_parameter` with the migration that seeds it and review the workspace's `ai` registry versions. |
| `setting-references` | A function in schema `erev` references a `current_setting` name outside the settings docs/04-DATA_MODEL.md lists (`app.tenant_id`, `app.user_id`, `app.entity_scope`, `app.platform_scope`, `app.data_fix_ticket`); the finding names the function and the setting (05 REL-07) | An undocumented session setting could steer row security or a trigger. Find the revision that created the function; remove the reference with a forward-fix revision, or document the setting in 04 first. |

### Production checks (05 SAR-40)

Under `EREV_ENV=production` (hosted staging and the compose production profile included) fifteen
further checks follow the six above, in this order: `email-backend`, `integration-urls`,
`cors-origins`, `session-cookie`, `defusedxml`, `partition-window`, `release-stamp`, `key-provider`,
`key-version-pin`, `recovery-provider`, the warning-only `anthropic-key`, `operator-alerts`,
`lock-budget`, `master-keys` and the warning-only `index-conditions`. Outside `production`
they do not run and print nothing; `--db dev`, `test` or `e2e` switches `EREV_ENV`, so they run only
in a production process checked without `--db`. The compose verification profile (05 DPL-16) is not
doctored and lies outside SOP-6 evidence; there is no `EREV_DOCTOR_PROFILE=verification` exemption,
because an exemption would bypass a fail-closed production check (D-97 (33)). A warning prints as `WARN <check>: <finding>` and
does not fail the command. Two further rules apply in `production`: a check whose observation the
build cannot collect (for example the connection list before the database collector exists) fails
closed with `FAIL <check>: <observation> was not collected`, and a check over a setting this build
does not define yet prints `WARN <check>: <variable> is not defined by this build (pending lane
<n> merge)` instead of a result, even when the environment supplies a value for it: the value is not
read until the owning lane's build defines the setting. The predicates live in `controls/doctor.py` (dev-guide
DG-MK-doctor).

How the command collects. Under `production` the command collects every observation once, before the
checks run, through the collectors composed in `cli.py` from `controls/doctor.py` (`production_collector`):
the settings snapshot (non-secret values of `Settings`; the recovery URLs as set or unset only); `openpyxl`;
`release-manifest.json` at the repository root (05 REL-03); the key ring (the provider's current `security-hmac`
key id through `KeyRing.current_security_key_id()` and a key-derivation probe of that id; the accessor arrives with
lane P2, so until then the provider observation is not collected and `key-version-pin` fails closed while
`key-provider` still passes for `local`); the tenant directory's `ACTIVE` integration connections (04 T-INT-01,
read once per workspace through a read-only tenant session; not collected until the INT lane's table exists);
the partition catalogue (the `pg_inherits` bounds of the PT-MPE and PT-MOC parents, `DEFAULT` excluded); the
lock table (the server's `max_locks_per_transaction`, `max_connections` and `max_prepared_transactions`, the partition
lock footprint and the relation count of the catalogue, read as `erev_app`); and the index keys (what the
catalogue check of 04 NC-20 answers for the indexes of the tables with a row-level-security policy, read as
`erev_app`; it reads the system catalogues and no table). The
Anthropic key resolves from `ANTHROPIC_API_KEY`, or under `gcp` from the Secret Manager reference `anthropic-api-key`
(05 KEY-10). Every member carries provenance (source, collection instant, error); a collector that fails or that this
build cannot compose reports in the FAIL line as `FAIL <check>: <observation> was not collected: <reason>`, where
the reason is either a code-owned pending-lane reason (this build lacks a table, module or accessor) or the
exception's type with a fixed, code-owned description of what the collector attempted — never the exception's
message text, which is untrusted (Codex P4B-R1); the same rule holds for the key-provider probe detail. The tenant
directory is read once for the baseline `audit-chain` and `ai` checks
and for the connection list, so one run still records exactly one `PLATFORM_SCOPE_USED` security event.

Startup subset (05 SAR-40 rev 1.53). Two of these checks are also applied without the command: the api and the worker evaluate
`email-backend` and `master-keys` on their own settings when they start and refuse to start when either fails (the api exits 3,
the worker 1, before any database connection; the log event `startup.refused` lists the findings). Both read configuration only.
The operator commands other than `erev doctor` and `erev verify` evaluate the same two checks and refuse to run (exit 3, the
`FAIL` lines on stderr); `erev migrate` is not an operator command in this sense.
`integration-urls` is not applied at startup: a connection's base URL is a workspace's own data, and a start that depended on it
would let one workspace stop the deployment. The rule is enforced elsewhere: under `production` a connection cannot be created
or updated with a base URL that is not a public `https` address (422 `validation-failed` on `base_url`), and the destination
guard refuses such a URL when a sync calls it ("Outbound webhooks"). The check finds a row saved before that rule.

What the command writes (SOP-1, SOP-7 inventory). `erev doctor` runs on demand from the CLI (`make doctor`; the
hosted runbook steps RB-02 and OPR-11 (3)); no job, startup hook or schedule runs it. It writes one
`PLATFORM_SCOPE_USED` security event (T-PLT-06) when it reads the tenant directory and nothing else: no `audit_event`
(the checks change no row), no `control_execution` row until T-PLT-39 (SOP-1) exists, and no controls-report entry
(REQ-CTL-005 has no designated CTL in 03 §4.1; the doctor is M-PM-05 evidence and its tests carry no control
marker; `release-stamp` overlaps CTL-032's impact paths, whose tagged test belongs to lane P1's manifest work). Related
automatic checks that do run elsewhere: the REL-03 release stamp at api and worker startup, the UPL-05 `DEFUSEDXML`
startup self-test, and SCH-13 `partition_window_check` (warns from 24 months out; lane P2).

| Check | Fails when | Response |
|---|---|---|
| `email-backend` | `EREV_EMAIL_BACKEND` is `fake`, or it is `smtp` and `EREV_SMTP_HOST` or `EREV_SMTP_FROM` is not set, or `EREV_SMTP_CA_FILE` is set and is not a readable PEM bundle of certificates (05 CFG-17, CFG-18). `WARN`, not a failure: `EREV_SMTP_PRIVATE_RELAY` is on | With `fake`, invitations, password resets and alerts are written to files nobody reads; with `smtp` and no relay or sender, or with a bundle that cannot be read, every send fails. Set `EREV_EMAIL_BACKEND=smtp` with the CFG-18 variables, and mount the bundle where the variable says. A production api or worker refuses to start on a finding. The warning states that the operator admitted a relay on a private or loopback address ("Outbox and email"); it needs no action when that is intended. |
| `integration-urls` | An `ACTIVE` integration connection has a loopback, private, link-local or unspecified address, `localhost`, a `.localhost`, `.local` or `.internal` name, or a single-label host as its base URL (the finding names the workspace and the connection code) | The connection points at a mock or an internal host. Disable it or set the provider's public endpoint; production never reaches the in-process mock routers (DG-API-09). |
| `cors-origins` | `EREV_CORS_ORIGINS` contains `*` (05 SAR-12) | List the exact SPA origins or leave the variable empty (same-origin serving); `create_app` refuses the wildcard as well. |
| `session-cookie` | `EREV_PUBLIC_ORIGIN` names `127.0.0.1`, `localhost` or `::1`, or its scheme is not `https` (05 SAR-09; DG-KRN-AUTH-07) | Serve the SPA from an `https://` origin on a public host name. The compose verification profile fails this check by design (DPL-16 does not run doctor). |
| `defusedxml` | `openpyxl.DEFUSEDXML` is false (05 UPL-05) | The `defusedxml` package is missing from the runtime environment; rebuild the image from the lock file. |
| `partition-window` | The last bounded partition of `audit_event`, `schedule_line` or `subledger_line` ends within 12 months of the check, or a table has no bounded partition (04 §1.6 rule 2) | Extend the window with a forward-fix revision (RB-12). SCH-13 warns from 24 months out. |
| `release-stamp` | `release-manifest.json` is absent (an observation reporting absence fails even without a collector error), or names another engine version or schema head (05 REL-03) | The image was built without `make release-manifest` or from another commit; rebuild and redeploy. |
| `key-provider` | `EREV_KEY_PROVIDER=gcp` without `EREV_GCP_PROJECT` or `EREV_GCP_KMS_KEK`, or the provider probe fails (05 CFG-11, CFG-13) | Check the service account's Secret Manager and KMS grants (05 DPL-33) and the CFG-13 ids. `local` passes: it is the compose shape. |
| `key-version-pin` | `EREV_SECURITY_HMAC_SECRET_VERSION` is unset or not a positive integer (ASCII digits), the provider's current `security-hmac` key id was not collected or is malformed, or the pin differs from that key id's version (05 KEY-03): a configured pin never counts as verified without the collected current identity | Pin the version the deployment signs with; after a rotation, update the pin and redeploy. A missing current identity means the key-provider probe did not run: check the probe before the pin. |
| `recovery-provider` | `EREV_RECOVERY_PROVIDER` is neither `NATIVE` nor `MANAGED`, contradicts `EREV_KEY_PROVIDER`, `NATIVE` lacks `EREV_BACKUP_URL` or `EREV_RESTORE_ADMIN_URL`, or `MANAGED` has either set (05 CFG-30; D-95) | Correct the recovery configuration (RB-04). An unset variable defaults from `EREV_KEY_PROVIDER` (`local` to `NATIVE`, `gcp` to `MANAGED`). |
| `anthropic-key` (warning) | `EREV_AI_PROVIDER=anthropic` and no `ANTHROPIC_API_KEY` secret resolves (05 KEY-10) | AI calls fail until the secret exists; the command still exits 0. |
| `operator-alerts` | Neither `EREV_OPERATOR_ALERT_EMAIL` nor `EREV_OPERATOR_ALERT_DELIVERY=log-only` is set (05 OPR-24, CFG-31) | Operator alerts (chain verification failures, partition window) would reach nobody. Name a recipient, or set `log-only` to acknowledge that the log is the only destination. |
| `lock-budget` | `max_locks_per_transaction × (max_connections + max_prepared_transactions)` of the server is smaller than `⌊0.8 × max_connections⌋ ×` the partition lock footprint `+` the relations of the database (05 §2.7); the finding names the settings, the requirement and the smallest sufficient `max_locks_per_transaction`. It also fails when schema `erev` has no partitioned table | Set `max_locks_per_transaction` to at least the value the finding names and restart PostgreSQL ("PostgreSQL lock table" under "Partition window and ANALYZE"). A reload does not apply it. |
| `master-keys` | Under `EREV_KEY_PROVIDER=local`, one of `EREV_ENCRYPTION_KEY`, `EREV_AUDIT_HMAC_MASTER_KEY` and `EREV_SECURITY_EVENT_HMAC_KEY` is a placeholder (fewer than 16 distinct byte values among its 32), or two of them hold the same value (05 CFG-26); the finding names the variables, never a value. `gcp` passes: the keys are not used | Generate each key with `python3 -c "import secrets; print(secrets.token_hex(32))"` before the first start. On a deployment that already holds data, replacing a key is a rotation ("Master-key backup and key rotation"), not an edit. A production api or worker refuses to start on this finding. |
| `index-conditions` (warning) | An index of a table with a row-level-security policy has a key the policy cannot use to bound a scan and is not on the release's list of the indexes meant so: the line names `<table>.<index>` and why. Or an index of that list is not in the schema with the key the release gave it: the line starts with `-.<index>` (05 §2.7; 04 NC-20). Every release is tested with no finding, so a line here means that this schema is not the release's: an index created or dropped outside `erev migrate`, or a database at another revision (see `release-stamp`) | The command still exits 0 and a rollout goes on: a read entered through such an index gets slower as a workspace grows and is never wrong. Find the change and return to the release's schema as `erev_owner`: drop the extra index (`DROP INDEX CONCURRENTLY erev.<index>`; without `CONCURRENTLY` on a partitioned table), or create the missing one again as the `Keys` line of its table in docs/04-DATA_MODEL.md defines it. If the index was built by hand because a read was slow, report the read: the remedy is an index whose key the policy can use, delivered by a revision (dev-guide DG-KRN-DB-10). |

## Backup and restore

Runbook entry RB-04 (05 §7.2 OPR-08, OPR-09, OPR-10, OPR-14, OPR-15; §7.3 OPR-11, OPR-13, OPR-16, OPR-17; §6.4 SAR-04; dev-guide DG-MK-backup, DG-MK-restore-verify; 03 REQ-OPS-013, REQ-SEC-002). A restore always goes into a clone, which is verified and then cut over to. Production data is never restored in place, no tenant command performs a restore (REQ-PLT-024), and `restore-verify` refuses any target that is not an `erev_rv_*` database.

### Recovery objectives

| Scope | RPO | RTO | Mechanism |
|---|---|---|---|
| Hosted production database (OPR-08) | RPO ≤ 15 minutes | RTO ≤ 4 hours | Cloud SQL automated daily backups retained 30 days and point-in-time recovery over the transaction-log window (`pitr_log_retention_days`, default 7); restore is a PITR clone and a cutover |
| Hosted production file store (OPR-09) | 0 for committed references | ≤ 4 hours | Regional bucket with object versioning and 7 days of soft delete under CMEK `erev-gcs`; a committed `file_object` row always has its bytes because the object is written before the row commits (OPR-13) |
| Erasure completion (OPR-10) | n/a | n/a | A shredded sidecar stays recoverable from soft delete for 7 days and database backups hold no data keys; erasure is complete 7 days after `file.shred` |
| Staging (OPR-14) | 24 hours | 24 hours | Daily backups, no PITR |
| Local and self-hosted (OPR-15) | The self-hoster's choice; default one `make backup` a day | n/a | `pg_dump -Fc`, the files tarball, the `.env` copy, the chain and key digests and the manifest under `.data/backups/` |

The hosted objectives are the REQ-OPS-013 commitments. They hold only while point-in-time recovery is enabled with at least the log retention above; the instance name, edition and retention are unknown inputs (UI-2) and the quarterly restore test (RB-06) is the evidence that they are met.

Measured locally (lane OPS drill of 2026-09-30 UTC on commit `d25fcce0`, record `docs/reviews/loop/sprint/OPS.md`: an Apple-silicon laptop, PostgreSQL 17.11 in a container, the 8 demo workspaces, a 129 MB database, a 16 MB dump and 316 stored files): `make backup` took 15 s (8 s inside the script, the rest is the execution context); the database volume was then destroyed and a fresh server with the RB-11 roles was ready 9 s later; `make restore-verify` took 28 s (restore 11 s, migrate 1 s, verify 4 s, doctor 1 s) and found all 11 backup-time anchors; a verified clone existed 37 s after the destroy began; the recovered evidence lagged the restore point by 3 s; and the row counts of all 691 tables equalled the source's except `security_event` (+2, the verifier's and the doctor's own events). These are drill figures on demo-sized data: they bound neither a cutover RTO (a drill performs none) nor production volumes, and the local RPO stays the backup cadence the self-hoster chooses.

### Local and self-hosted backup

```sh
make backup
```

Prerequisites: the api and worker are stopped (`make dev-down`; the target refuses while `.run/api.pid` or `.run/worker.pid` names a live process, see "Consistency" below; `ALLOW_LIVE=1` overrides and the manifest records `quiesced: false`); a `.env` that is the one the application reads (`EREV_DOTENV` pointing elsewhere is refused) and holds the three master keys, which must equal any `EREV_*_KEY` set in the environment, so the copy restores exactly the keys the verification used; and `EREV_BACKUP_URL` in the environment or in `.env`, naming the same database as `EREV_DB_OWNER_URL` as the backup role `erev_backup` that the database administrator provisions (RB-11): `NOSUPERUSER`, `BYPASSRLS`, read-only through `pg_read_all_data`, used for backups only. `EREV_BACKUP_URL`, `EREV_DB_OWNER_URL` and `EREV_DB_APP_URL` must route to one server, port and database, and the three servers actually reached must answer one identity; a same-named database on another host or port is refused before anything runs. No other `erev_app` or `erev_owner` session may be connected to the database while the backup runs: the preflight counts them in `pg_stat_activity` (with the backup role, during the identity check) and refuses with `N application session(s) (erev_app or erev_owner) are connected to <database>`; two local PID files do not prove the absence of external writers. `ALLOW_LIVE=1` overrides both checks and the manifest records `quiesced: false`. The `.env` is hashed before anything is written and its copy is hashed again after it is written; a difference fails the run (see "Consistency"). `pg_dump` as `erev_owner` is refused with `query would be affected by row-level security policy for table "…"`: every tenant table carries `FORCE ROW LEVEL SECURITY` and the owner holds no policy (04 DB-14), so the application roles can neither dump nor load rows. The URL is read once and reaches `pg_dump` only as `PG*` connection variables; nothing prints it. `scripts/check_env.py --db` reports whether `EREV_BACKUP_URL` and `EREV_RESTORE_ADMIN_URL` are present and refuses a malformed one (names only, never values).

Expected output:

```text
SUPERVISOR TARGET backup (D-48a)
gate-context: backup runs in <worktree>/.run/gates/ctx-backup-<build sha>-<pid> (<build sha>, tree <tree sha>)
== backup: exec ==
backup: database erev -> erev-20260919T183359Z (quiesced=true)
erev-20260919T183359Z.digests.json
erev-20260919T183359Z.dump
erev-20260919T183359Z-files.tar.gz
erev-20260919T183359Z.env
erev-20260919T183359Z.manifest.json
OK backup
```

On a committed tree the script runs from an execution context, a clone of the commit (dev-guide DG-MK-00i), and the target hands it this checkout's live data: the file store (`EREV_FILE_ROOT`, resolved against the checkout when relative), the PID files of `.run/`, the backups directory and a copy of `.env`. With uncommitted changes the second line reads `gate-context: backup runs in the worktree (worktree-dirty (development; not release evidence)); commit first for release evidence`; the backup set is the same, its report is not release evidence.

| File | Content | Why it is in the backup |
|---|---|---|
| `erev-<timestamp>.digests.json` | The `erev verify --all-tenants` document taken first: every tenant's audit chain head and latest SAR-31 digest, every book's ledger seal head, the security chain head, the file inventory with plaintext hashes and the key versions in use | `restore-verify` anchors the restored chains into these heads (OPR-11 (3) and (4)); a `FAIL` here still writes the backup and fails the target, so the evidence is kept before anyone reacts (RB-08) |
| `erev-<timestamp>.dump` | `pg_dump --format=custom` of the whole database | The schema, every row, the Procrastinate objects and `alembic_version` |
| `erev-<timestamp>-files.tar.gz` | `EREV_FILE_ROOT` without `.incoming/` partials | The stored objects and their `.dek` sidecars; a database without them has rows that point at nothing |
| `erev-<timestamp>.env` (mode 0600) | A copy of `.env` | The master keys (RB-05): without them every audit chain fails verification and every encrypted file is `undecryptable` |
| `erev-<timestamp>.manifest.json` (schema `erev-backup-manifest/2`) | SHA-256 and size of exactly the four files above, the database name, schema revision, build sha, `snapshot_started_at` and `snapshot_finished_at` (around `pg_dump`; the restore point is the start), `created_at` (the manifest instant, which is never the restore point), `quiesced`, tool versions and the digests result; every instant is an RFC 3339 date-time with an offset (`YYYY-MM-DDTHH:MM:SS[.frac](Z|±HH:MM)`; week dates, ordinal dates, a space separator or missing seconds are refused) and the instants are ordered `started_at` ≤ `digests.generated_at` ≤ `snapshot_started_at` ≤ `snapshot_finished_at` ≤ `created_at` | `restore-verify` refuses a backup whose manifest is incomplete, names other members, carries a malformed hash or size, belongs to another backup id, or whose files do not match it |

`.run/reports/backup/report.json` records the run (DG-MK-00g). Keep the five files together and treat the set as secret material: the `.env` copy is the key. Schedule the target daily from the account that owns `.env`, keep at least 30 daily sets, and store them on an encrypted volume the backup operator alone can read.

### Consistency: what a backup captures while the system changes

The five files are taken one after the other: digests, dump, files tarball, `.env` copy, manifest. The dump is one consistent snapshot of the database (the restore point); the file store is read after it. `make backup` therefore requires the api and worker to be stopped (`quiesced: true`), which is the local and self-hosted protocol; hosted production uses Cloud SQL backups and PITR, whose snapshots are consistent without stopping anything, and the file store's write-before-commit rule (OPR-13). When a backup is taken live (`ALLOW_LIVE=1`), the possible races and their outcomes are:

| Change between the dump and the tarball | In the restored clone | Detected by |
|---|---|---|
| A file uploaded (object and sidecar written, row committed after the dump) | Object present, no row | Not a failure: an unreferenced object, deleted by the orphan sweep (SCH-14) |
| A file committed before the dump but still being written | Impossible: the object is linked atomically before its row commits (OPR-13) | n/a |
| A shred after the dump | Row not shredded, sidecar gone | `erev verify`: `missing_sidecar`, a FAIL; the operator finds the shred in the live audit log and records the file as erased after the restore point |
| A shred decided before the dump whose key the file store had not yet destroyed when the tarball was taken (the store did not answer in between; RB-14) | Row shredded with an empty `shred_completed_at`, sidecar present | `erev verify`: `shredded_sidecar_present`, a FAIL until the shred is completed — the worker's sweep destroys the key in the clone as it would have in the source, and the file is refused by its row meanwhile |
| An MFA seed or webhook secret sealed after the dump | Not in the clone | n/a (the row is absent too) |
| A master key changed (a new `.env`) | The `.env` copy carries the keys the digests used, checked before the dump | `make backup` refuses an environment key that differs from the file |
| `.env` edited while the backup runs | Cannot ship: the copy's SHA-256 must equal the hash taken at preflight, and the effective keys are verified on the copy itself | `make backup` fails at the `.env` step (`.env changed during the backup`), writes no manifest, and the set is not a backup; the manifest of a successful run records `env_copy_sha256` |
| A session of `erev_app` or `erev_owner` other than the backup's own | Any of the rows above may happen | The preflight counts the sessions in `pg_stat_activity` and refuses unless `ALLOW_LIVE=1` (`quiesced: false`) |

The intent of the design is that none of these produces a clone that verifies but is wrong: each inconsistency in the table is either harmless or a `FAIL` of `restore-verify`. That holds for the races listed; it is not a proof over every possible concurrent write, and the script does not serialize the phases. A live backup is a detection point, not a recovery point; quiesce for the recovery point.

**What the writer check does and does not prove.** The `pg_stat_activity` preflight rejects `erev_app` and `erev_owner` sessions observed at that instant; it cannot prevent a session that connects afterwards, and it does not hold a lock across the digests, dump, archive and `.env` copy. Sustained writer exclusion during the backup window is therefore an operational requirement of RB-04, not something the script establishes: put the deployment in maintenance mode or scale the api and worker to zero (hosted: Cloud Run revisions at zero instances; local: `make dev-down`) for the whole run, and keep it that way until `OK backup` is printed. Likewise the `.env` hash comparison detects a persistent change of the file between preflight and the copy; it does not freeze the bytes each verification process read. A backup taken without that exclusion is `quiesced: false` evidence to be re-taken, not a recovery point.

### Security-key inventory in the backup evidence (P2/P6 integration)

The security-event chain (T-PLT-06) is one global chain whose rows may be signed under several numbered keys (`security-hmac:<n>`; rows written before migration 0055 are attributed to `security-hmac:1`), and the deployment signs new rows under the pin `EREV_SECURITY_HMAC_SECRET_VERSION`. `erev verify --all-tenants` records, in `security_chain`, the key of the chain head (`head_key_id`), the pin (`current_key_id`) and every key id the rows name plus the pin (`required_key_ids`; rows at versions 1 and 3 under pin 5 need {1, 3, 5}), with the availability of each id under `key_versions.security_hmac`; a required id the key provider does not serve, or a pin behind the chain head, is a `FAIL`. `make backup` copies the pin and the required ids into the manifest (`security_hmac_pin`, `security_required_key_ids`; key ids only, never material) and `restore-verify` binds them to the digests document. A database backup alone proves neither secret retention nor verifier access: a restored deployment must be able to serve every id in `required_key_ids`, and the restore drill checks exactly that.

### Encryption at rest

- Hosted: Cloud SQL and both buckets use the customer-managed keys `erev-cloudsql` and `erev-gcs` of the `kms` Terraform module when `use_cmek = true` (the default); automated backups and PITR logs inherit the instance key (05 SAR-04, KEY-01, KEY-02).
- Self-hosted: the self-hoster is obliged to encrypt at rest the database volume, the file store (`EREV_FILE_ROOT`) and every location that holds backups (the dump, the files tarball and above all the `.env` copy), for example with an encrypted volume, and to restrict those paths to the backup operator (REQ-SEC-002). eRev Cloud encrypts file contents and secrets in the application layer (SAR-07) but not the database pages.

### Restore into a clone (local and self-hosted)

```sh
export EREV_RESTORE_OWNER_URL=postgresql://erev_owner:…@127.0.0.1:5432/erev_rv_restore   # the clone, as erev_owner
export EREV_RESTORE_APP_URL=postgresql://erev_app:…@127.0.0.1:5432/erev_rv_restore       # the clone, as erev_app
export EREV_RESTORE_ADMIN_URL=postgresql://<bypassrls role>:…@127.0.0.1:5432/erev_rv_restore
make restore-verify BACKUP=erev-20260919T172644Z      # BACKUP=latest takes the newest manifest
```

The database administrator creates the empty clone database `erev_rv_<name>` owned by `erev_owner` (DG-ENV-13 allow-list) on the isolated server, with the statements of RB-11 "The backup role and the restore-target admin". The admin URL names the restore-target admin of that isolated server only: `erev_restore_admin`, a `BYPASSRLS` non-superuser member of `erev_owner` (RB-11; the isolated server's superuser also works and is recorded as such); `pg_restore` needs it for the same reason `pg_dump` does, and ownership comes back as `erev_owner` through the membership. It is never a production credential. `RESET=1` drops schema `erev` and the Procrastinate objects of a clone that was used before; nothing else is ever dropped.

Before it resets, restores, extracts or removes anything, the target refuses: a `BACKUP` that is not `erev-<yyyymmdd>T<hhmmss>Z` or `latest`; a manifest that is not schema `erev-backup-manifest/2`, names another backup id, omits one of the four members, lists an extra or traversing name, or carries a malformed hash or size; a member whose hash or size differs; an archive member outside the file root, with `..`, absolute, or a link; a digests document that is empty, untyped or incomplete (a tenant without an explicit head, where an empty chain is `last_chain_seq 0` with `last_hmac null`; a nonzero audit, security or ledger head without its hash; a key entry that is not `{key_id, available}`; file entries without a known status and hash, or counts that do not add up) or not the one the manifest describes; a manifest instant that is missing, has no offset or is out of order (`started_at`, `snapshot_started_at`, `snapshot_finished_at`, `created_at`, `digests.generated_at`; the restore point is never taken from a later field); three target URLs that do not route to one server, port and `erev_rv_*` database, or three connections that answer different server identities; a restore directory outside `.run/restore/` or that is a link. It then runs, in order: `pg_restore --exit-on-error --single-transaction` as the admin, the extraction under `.run/restore/<backup id>/files` through Python's data filter, and, under the master keys read from the backup's `.env` copy, `erev migrate` on the clone (forward-fix under the release being validated), `erev verify --all-tenants --db erev_rv_<name> --expect <backup id>.digests.json` and then `erev doctor --db erev_rv_<name>` (the doctor's directory read appends a security event, which must not count as recovered evidence). A backup whose own verification had failed is restored and verified, and the run then fails naming that failed evidence: it is never a clean baseline. Expected output:

```text
SUPERVISOR TARGET restore-verify (D-48a)
gate-context: restore-verify runs in <worktree>/.run/gates/ctx-restore-verify-<build sha>-<pid> (<build sha>, tree <tree sha>)
== restore-verify: exec ==
restore-verify: backup erev-20260930T060637Z
restore-verify: manifest, four members, archive and digests verified (baseline result at backup: PASS)
restore-verify: clone security pin security-hmac:1 (backup pin security-hmac:1, chain head under security-hmac:1, forward rotation false)
restore-verify: target endpoint erev_rv_restore bound (one server identity on owner, app and admin)
restore-verify: preflight complete; no side effect so far
<timestamp> [info     ] db.engine_created              database=erev_rv_restore engine=owner host=127.0.0.1 port=5432
restore-verify: target database erev_rv_restore is ready
restore-verify: pg_restore into erev_rv_restore done in 11s
restore-verify: files extracted under erev-20260930T060637Z/files
restore-verify: restored schema revision 0072
restore-verify: erev migrate on the clone done in 1s (head 0072)
OK security-chain: 306 events checked; head 306
OK avenmoor audit-chain: 9209 events checked; head 9209; digest at 9208 (gap 1)
OK avenmoor ledger ASC606: 179 seals checked
…
OK key-versions: 1 security, 8 audit, 1 kek ids; 12 of 12 envelopes opened
OK expected: 11 backup-time anchors from erev-20260930T060637Z.digests.json (8 tenants, result PASS); 0 findings
OK verify
OK row-level-security: 128 tenant tables have forced row level security and a policy
…
OK setting-references: 82 functions reference only the documented app.* settings
restore-verify: drill duration 19s (restore 11s, migrate 1s, verify 3s, doctor 1s); no cutover RTO in a drill; record .run/reports/restore-verify/report.json
OK restore-verify
```

The `OK` lines after `OK verify` are the doctor's checks; the script prints them without a closing `OK doctor` line. With `RESET=1` on a clone used before, a line `restore-verify: schema erev and the Procrastinate objects dropped in erev_rv_restore (RESET=1)` precedes `target database … is ready`. The restore directory `.run/restore/<backup id>/` of this checkout keeps the extracted file store (`files/`) and the logs of the run (`run/migrate.log`, `run/verify.log`, `run/doctor.log`), and `.run/restore-pg_restore.log` the restore's own output; they outlive the execution context the script ran in.

`.run/reports/restore-verify/report.json` holds the restore-test record of RB-06 (`restore_test_record`: backup id, restore duration, verification result, the baseline result at backup) and the measurements under `restore`: `restore_point` (the dump's `snapshot_started_at`, never the manifest instant) with its `restore_point_basis`, `recovery_age_seconds` (from the restore point to the measurement: what a recovery started now would lose), `latest_recovered_evidence_at` and `evidence_lag_seconds` (the recovered data's own newest evidence; the verifier's appended events are excluded and counted in `verifier_events_excluded`; a negative lag is reported as `evidence_after_restore_point`), `per_tenant_digest_gap_events` (OPR-11 (4)), `drill_duration_seconds` and `phase_seconds`, and `cutover_rto_seconds: null` because a drill performs no cutover: the hosted RTO of OPR-08 is measured in the annual exercise (RB-06). A `FAIL` line ends the run at once; the clone stays for inspection.

Cutover, once the clone verified: stop the api and worker (`make dev-down`; hosted see below), point `EREV_DB_OWNER_URL` and `EREV_DB_APP_URL` at the clone and `EREV_FILE_ROOT` at the extracted files, `.run/restore/<backup id>/files` by its absolute path (or copy them back over the file root), start the stack, then record the restore in every workspace's audit log and notify the Tenant Admins by email (no notification kind exists for it yet):

```sh
backend/.venv/bin/erev restore-applied --instant 2026-09-19T17:26:44Z --backup erev-20260919T172644Z \
  --digests .data/backups/erev-20260919T172644Z.digests.json
```

The command appends one `platform.restore_applied` event per ACTIVE workspace as the SYSTEM principal, naming the restore instant, the backup, the previous chain head from the digests and, in its own output, the new head; the chain verifies afterwards with that event as its head. Keep the replaced database read-only as evidence until the post-incident review closes (RB-10). Never run `restore-applied` against the source that was replaced.

### Recovery provider (ruling D-95)

`EREV_RECOVERY_PROVIDER` selects how a deployment backs up and recovers; it defaults from `EREV_KEY_PROVIDER` (`local` → `NATIVE`, `gcp` → `MANAGED`) and an explicit value that contradicts the key provider is a configuration error (`scripts/check_env.py --db` reports it).

| Provider | Backup | Drill | Where |
|---|---|---|---|
| `NATIVE` | `make backup`: the read-only `BYPASSRLS` role `erev_backup` dumps, the files tarball, the `.env` copy, the digests and the manifest (this section) | `make restore-verify` into an isolated `erev_rv_*` database as `erev_restore_admin` | Self-hosted PostgreSQL and the compose stack, where an authorised provisioner can create the roles: specifying `BYPASSRLS` requires a superuser or an actor that already holds `BYPASSRLS`, membership does not inherit the attribute, and `CREATEROLE` alone cannot bootstrap it |
| `MANAGED` | Cloud SQL automated backups (retained 30) and point-in-time recovery (05 OPR-08), control-plane operations authorised by IAM, independent of row-level security; the pre-migration on-demand backup (OPR-16) | A clone into the restore-test instance (`restore_test_instance`, UI-P6-2) verified under the application roles with `erev verify --all-tenants`, recorded as the managed restore-test record of RB-06 | Hosted staging and production |

Hosted deployments have no `erev_backup` and no `pg_dump` path. Cloud SQL gives customers no superuser; `cloudsqlsuperuser` carries `CREATEROLE`, `CREATEDB` and `LOGIN` only, and Google documents no customer procedure that grants `BYPASSRLS`, so the native role is **unestablished on Cloud SQL** and the design does not depend on it. `FORCE ROW LEVEL SECURITY` (04 DB-14) stays in force everywhere: no owner or application bypass, no permissive backup policy, no impersonation and no partial row-security dump is used on either provider (measured: `pg_dump` as `erev_owner` is refused). `make backup` and `make restore-verify` refuse under `MANAGED`. Whether Cloud SQL's managed export (`gcloud sql export sql`) is bound by the same restriction is an unknown input (UI-P6-1) to be settled by one staging test against a `FORCE ROW LEVEL SECURITY` table with a row-count comparison; it is not a backup path until then. A database backup alone does not evidence coordinated file, key and shred restoration or an achieved RPO: the managed record below binds the external state too.

### Hosted restore: clone and cutover (05 OPR-11)

1. Declare the incident (RB-10): SEV-2 "restore required", or the severity of the incident that caused it.
2. Create the point-in-time clone; Cloud SQL always creates a new instance and cannot restore onto an existing one:

   ```sh
   gcloud sql instances clone <production instance> <production instance>-restore-<yyyymmdd> \
     --point-in-time='2026-09-19T17:26:44Z'
   ```

   A restore from a daily backup instead of PITR is `gcloud sql backups restore <backup id> --restore-instance=<clone instance> --backup-instance=<production instance>` into a clone created first.
3. Run step (3) against the clone under the application roles only (no `BYPASSRLS` role exists or is needed hosted): from the migration job's identity (the only holder of `erev-db-owner-url`, RB-11) with the clone's connection name in `EREV_DB_OWNER_URL` and `EREV_DB_APP_URL` and the production key provider, `erev migrate` (as `erev_owner`; forward-fix onto the release being validated), then `erev verify --all-tenants --output verify.json` and `erev doctor` (as `erev_app`). The document verifies every chain, every stored file against its sidecar and every envelope under its KEK, and compares each tenant's `audit_chain_head` with its latest digest row and digest file (SAR-31); compare its `tenants[].digest.last_hmac` with the copy in the digest bucket (`gcloud storage cat gs://erev-audit-digests-<env>/<object>`), which the database cannot have altered. The recovery measurements are the same as the local drill's (RB-06), with the PITR instant or the backup's snapshot time as the restore point.
4. Record the gap: `tenants[].gap_events` (events after the last digest) and `restore.data_loss_window_seconds` go into the incident record; the tenants whose gap is not zero are the ones to tell.
5. Cut over: add new versions of the secrets `erev-db-owner-url` and `erev-db-app-url` naming the clone (`gcloud secrets versions add erev-db-owner-url --data-file=-`), pin those versions in the release configuration and deploy a new revision through the release pipeline with the same image digests (OPR-07); never edit a running revision by hand.
6. `erev restore-applied --instant <PITR instant> --backup <clone instance name>` against the new production database, then notify every Tenant Admin (within 24 hours of confirmation when personal data was lost, PRV-12).

### The clone's signing pin (P2/P6 integration)

Before it resets or restores anything, `restore-verify` decides the pin the clone runs under from the backup's own evidence (`recovery_preflight.clone_security_pin`): the backup's `current_key_id`, which must not be behind the chain head it recorded (a backup whose pin is behind its own head is inconsistent evidence and is refused). The clone environment sets `EREV_SECURITY_HMAC_SECRET_VERSION` to that version explicitly; the restore host's own pin and its `.env` are never inherited, because a pin behind the restored chain head would let the verifier's first platform event append a backwards key transition (KEY-03; P2's writer fence refuses it). An operator may move the pin **forward** only, explicitly, with `RESTORE_SECURITY_HMAC_VERSION=<n>` (an intentional rotation on the clone): forward means above both the chain head and the pin the backup was taken under, so an override below the backup's pin is refused even when the head would admit it, and `forward_rotation` is true only when the clone's pin is above the backup's; the record says so:

```text
restore-verify: clone security pin security-hmac:1 (backup pin security-hmac:1, chain head under security-hmac:1, forward rotation false)
restore-verify: preflight complete; no side effect so far
```

A backwards or malformed override (`RESTORE_SECURITY_HMAC_VERSION=0`, `=latest`, or a version below the head) is refused at that step with nothing connected, reset or restored. The clone is driven by one binary, the release being validated (`erev migrate`, `erev verify`, `erev doctor` from the same checkout), so the drill never mixes a pre-admission revision with a form-2 writer against the restored chain (DG-KRN-AUD-08 cutover rule); an upgrade validation that deliberately runs two revisions is RB-16, not this drill. The report's `restore.security_hmac` carries `clone_pin`, `backup_pin`, `backup_head_key_id`, `forward_rotation`, `required_key_ids` and the ids the verifier `served` on the clone.

## Master-key backup and key rotation

Runbook entry RB-05 (05 §6.5 KEY-03 to KEY-05, SAR-23; §7.3 OPR-17; dev-guide DG-KRN-KEY-02, DG-KRN-KEY-05). There is no keyring file: the local provider derives every key from the three `.env` master keys, and hosted deployments hold them in Secret Manager and Cloud KMS.

| Key | Local (`EREV_KEY_PROVIDER=local`) | Hosted (`gcp`) | Recorded where |
|---|---|---|---|
| KEY-03 security HMAC key `security-hmac:<n>` | HKDF over `EREV_SECURITY_EVENT_HMAC_KEY` | Secret Manager `erev-security-hmac`, versions | every `security_event` is signed with it |
| KEY-04 key-encryption key `kek:<n>` | HKDF over `EREV_ENCRYPTION_KEY` | Cloud KMS `erev-app-kek` | `.dek` sidecars and every `secret_key_id` of MFA seeds and webhook secrets |
| KEY-05 tenant audit HMAC key `audit-hmac:<tenant id>:<n>` | HKDF over `EREV_AUDIT_HMAC_MASTER_KEY` | Secret Manager `erev-audit-hmac-<tenant id>`, versions | `tenant.audit_hmac_key_id`; `audit_event.hmac_key_id` on every event |

- Backup: `make backup` copies `.env` with mode 0600 into every backup set (OPR-17). A restore under another `EREV_AUDIT_HMAC_MASTER_KEY` fails every audit chain from sequence 1; under another `EREV_ENCRYPTION_KEY` every encrypted file is reported `undecryptable` and no MFA seed opens. Both were reproduced in the restore drill record.
- Hosted, keys are never destroyed: the KMS keys carry `prevent_destroy` and 30 days of destruction scheduling, and Secret Manager HMAC versions are never destroyed (OPR-17). The three CFG-26 master keys are escrowed by the platform owner (UI-4).
- Inventory before any change: `erev verify --all-tenants` lists every key id the data references and whether the running provider serves it; the line `OK key-versions: 1 security, 8 audit, 1 kek ids` and the `key_versions` object of the document are the evidence. A `FAIL <workspace> audit-keys` or an `undecryptable` file means an old version is still needed.
- Rotation: a new version is a new `<n>` (`kek:2`, `security-hmac:2`, `audit-hmac:<tenant id>:2`); old ids stay derivable locally and stay as versions hosted, so historical events verify and old sidecars unwrap. KMS rotation creates a new primary version and re-encrypts nothing, so no old version is disabled before `erev verify --all-tenants` proves it unreferenced. Rotating a master key value itself is not supported: chains cannot be re-signed, and files would need a rewrap of every sidecar.

The security HMAC keys are numbered versions, not one key: the backup evidence names every version the chain needs (`security_required_key_ids`) and the pin in force; a rotation to a new version must keep every earlier version retrievable by the verifier's identity (locally every version derives from the master key in `.env`; hosted, each numbered secret version must stay readable), or the restore drill fails naming the missing version.

## Restore-test procedure and record

Runbook entry RB-06 (05 §7.3 OPR-12; 03 REQ-OPS-013; dev-guide DG-MK-restore-verify). Restore tests prove the objectives of RB-04; a backup that was never restored is an assumption.

- Quarterly: an automated job in staging restores the latest production backup (the latest automated backup, or a PITR instant) into an isolated instance in a separate project, the restore-test project (UI-10), a fresh instance named by the Terraform variable `restore_test_instance` (P3b follow-up, UI-P6-2); it runs step (3) of OPR-11 under the application roles (`erev migrate`, `erev verify --all-tenants`, `erev doctor`) and stores the **managed restore-test record** (`erev_api.controls.recovery_managed`, schema `erev-managed-restore-record/1`) in the provider's evidence store: the backup bound to its project, source instance, backup id or PITR instant, operation status, start and end, engine, schema and release identity (a backup id is unique only within an instance); the restore's project, fresh instance, operation status and duration; the recovery interval (restore point = the PITR instant or the backup's completion, never the record instant; recovery age); the external state a database restore does not prove (file object generations pinned at backup time and observed after the restore, key-version references and the ones served, digest objects, shred tombstones); the tenant inventory and audit anchors from the verifier's document on the clone; the assurances (RLS forced, no bypass, no partial dump, no relaxed policy, no impersonation); and never an invented SHA-256 of provider-managed bytes. `validate_managed_record` refuses a pending, failed or wrong-instance backup, a non-isolated destination, missing bindings, drifted generations or unserved keys, a failed or unanchored verification and any relaxed assurance. Locally and self-hosted the same record is `restore_test_record` in `.run/reports/restore-verify/report.json`, written by `make restore-verify`, together with the `restore` measurements (restore point, recovery age, recovered-evidence lag, per-tenant digest gaps, drill duration and phases). A drill's duration is not the cutover RTO. The managed record also carries the security-key set derived from the source-bound baseline (`audit_anchors.baseline_security_key_ids`, `baseline_security_pin`) next to the clone's inventory and the ids the verifier opened; `validate_managed_record` requires every derived version to be referenced, served by the provider and opened by the restore verifier, so a self-declared list that is merely a subset of a self-declared available list is refused (missing historical version 3 and missing current version 5 are each named). The record retains the full baseline and the clone's verification document (`evidence`) with their hashes: the summaries are derived from those bytes when the record is built (a baseline or verification document whose head or pin falls outside its own required set is refused before any record exists) and re-derived from them when the record is validated, so a summary that differs from its evidence, a hash that differs from the retained document, or missing retained evidence is refused. The security-key inventory itself is lane P2's contract (`required_security_key_ids`), a hard import of the recovery module: a build without it does not import `erev verify` at all, and nothing is skipped or assumed.
- Annually: a full DR exercise of OPR-11 including the cutover in staging, measuring RTO against the 4 hours of OPR-08 and recording the observed RPO from `data_loss_window_seconds`.
- The isolated instance is never the production instance, the clone is deleted after the record is stored, and the record names the release (`build_sha`), the schema revision restored and the one migrated to.

```sh
make restore-verify BACKUP=latest RESET=1
cat .run/reports/restore-verify/report.json
```

Expected: `OK restore-verify` and a report whose `restore_test_record.verification_result` is `PASS`, `restore.expected_result` is `PASS` (every backup-time anchor found in the restored chains) and `counts.failures` is 0. Any `FAIL` is filed as an incident (RB-10) against the backup process, not against the clone. The files of a sandbox verify with the rest: a copied file lies under the key of the workspace the sandbox was copied from, and the verifier reads it there, as the sandbox does. A file reported `foreign_storage_key` is a row that names the object of a workspace that is neither its own nor its sandbox's source — a fault of the stored data, told apart from `undecryptable`, which is a key that does not open (the wrong `.env`).

### Rehearsal on a throwaway server

`make restore-drill` (dev-guide DG-MK-restore-drill) proves the recovery procedure and the tooling of the release in the checkout, not a deployment's backup. It starts a PostgreSQL container of its own, seeds the demo workspaces, backs them up, destroys the container with its volume, starts a fresh server, restores the backup there and verifies it, and compares the row count of every table of the clone with the source. It needs Docker, the PostgreSQL 17 client tools (`pg_dump`, `pg_restore`) and the `.env` of the checkout. It reads and writes nothing of a deployment: the server is compose project `erev-verify-drill` on `127.0.0.1:5446`, the backup role and the restore-target admin are created inside that container with passwords generated for the run, and the drill's backup set never reaches `.data/backups/`.

```sh
make restore-drill                      # the eight demo workspaces: about ten minutes
make restore-drill TENANTS=avenmoor     # a quicker rehearsal on one workspace
cat .run/reports/restore-drill/report.json
```

Expected: `OK restore-drill`, after one line that names the backup, the tables and rows of the source and of the clone, and the seconds from the destruction to the verified clone. In the report `result` is `verified`, `counts.tables_missing_in_clone` and `counts.tables_with_fewer_rows` are 0, `seconds` holds the measured durations, and `restore` and `restore_test_record` are the restore script's own; `backup.report.json` and `restore-verify.report.json` lie beside it with the logs of the steps. The clone may hold more rows than the source in `counts.tables_with_more_rows` tables: the verification appends its own security events. The server and the drill's directory, which holds the backup set with its copy of the master keys, are removed on every path.

| Final line | Meaning and action |
|---|---|
| `FAIL restore-drill: project erev-verify-drill holds … of another drill` | A drill is running on this Docker daemon, or one was interrupted. Wait for the running one. After an interrupted one, `make restore-drill RESET=1` first removes the container and the volume it left; never use it while a drill runs |
| `FAIL restore-drill: 127.0.0.1:5446 is in use` | Another program holds the port: `make restore-drill DRILL_PORT=<port>` |
| `FAIL restore-drill: the clone does not hold what the source held` | A table is missing in the clone or holds fewer rows (`row-counts.json` next to the report names it): the backup or the restore lost data. File it as an incident (RB-10) |
| `FAIL restore-drill: … (see restore-drill/<step>.log)` | The named step failed; the log lies next to the report. A `seed.log` ending in `ReleaseManifestError: the release manifest names another schema revision` means a `release-manifest.json` of another commit lies at the repository root ("Start" of the compose section): it is read only when the drill runs in place, in a checkout with uncommitted changes |

The deployment's own restore test is the procedure above it: `make restore-verify` of its latest backup into its isolated clone.

## Background jobs and the worker

Long operations run as `job` rows wrapping the Procrastinate task `erev.run_job`. The Procrastinate tables and functions live in schema `public` of each database; revision 0012 installs them and `make db-reset` drops them with schema `erev`.

### Run the worker

- `make worker` runs `backend/.venv/bin/erev worker` in the foreground on all eight queues (`compute`, `imports`, `close`, `outbox`, `reports`, `maintenance`, `integrations`, `ai`). The final line is `OK worker` after a clean stop.
- `erev worker --queues compute,close` restricts a worker to named queues for a hosted split. An unknown name exits 2 with `unknown queue <name>`. `EREV_WORKER_QUEUES` sets the same list; `--queues` overrides it.
- The worker writes `.run/worker.heartbeat` every 15 seconds (`--heartbeat-file` names another file). `erev worker --check` exits 0 while the file is younger than 60 seconds and 1 otherwise; container health checks call it.
- `EREV_WORKER_CONCURRENCY` sets how many tasks one worker runs at once. Separately, one tenant runs at most its `platform.job_concurrency` jobs (a TENANT registry value; default 4) across all workers; a job without a free slot stays `QUEUED` and is retried after 5 seconds.

### Job monitoring

Runbook entry RB-07 (05 JOB-06, JOB-07).

- `make status` shows the `worker` line, for example `worker pid=4242 alive port=- ready=ready`. `ready=not-ready` means the heartbeat file is older than 60 seconds: read `.run/worker.log` and restart with `make dev-down` and `make dev-up`. Hosted deployments run `erev worker --check` as the health check.
- Holders of `audit.read` for all entities list failed jobs with `GET /api/v1/jobs?state=FAILED` and queued work with `GET /api/v1/jobs?state=QUEUED&state=RUNNING`. The job's `problem` explains a failure.
- In the worker log, `job.retry_scheduled` marks a failed attempt that will run again and `job.failed` a job with no attempts left.
- The audit log records every job except the outbox transport kinds (`OUTBOX_RELAY`, `EMAIL_DELIVERY`, `WEBHOOK_DELIVERY`): `job.start` when it is deferred (by the person or API client whose command deferred it, or by the system for a scheduled job), `job.finish` with its final state and the problem's slug, and `job.cancel` when someone cancels it (04 T-PLT-27). Filter `GET /api/v1/audit-events` by these actions to reconcile the job list with the audit log.
- `job.fan_out_failed` and `job.sweep_failed` (error level) name a tenant, and for the sweeper the job, whose audit chain could not take the job's event — for example a tenant key the provider cannot serve. That tenant got no scheduled job, or that stalled job stays as it is; every other tenant is served. Both lines carry `error_class` and `error_at`, the module and line of the code where the error was raised, and never its message. Fix the tenant's key or chain; the next fan-out or sweep picks the tenant up.
- Dead letters: a job `FAILED` after its last attempt is not retried again. Before you start the operation anew, read the record the job worked on — the upload, the run, the batch — for what the job completed: a failed job keeps what it committed before it failed (the earlier chunks of a chunked job), and a job stopped as stalled keeps what it had committed by then and nothing after (05 JOB-06). Then fix the cause and start what is still to do. An outbox message becomes `DEAD` after ten failed dispatches (see "Outbox and email"), and a webhook delivery still failing 24 hours after creation is `ABANDONED`; list those with `GET /api/v1/webhook-deliveries?status=ABANDONED`.

### Stuck and failed jobs

- When the dispatch after a commit fails, the job stays `QUEUED` with an empty `procrastinate_job_id`. The worker's minute sweeper (`erev.sweep_jobs` on `maintenance`) defers such jobs again once they are 60 seconds old; no manual action is needed while a worker runs.
- A worker that dies while a job is `RUNNING` (killed, out of memory, a lost node) leaves the job `RUNNING` until the sweeper sees ten minutes without an update. It then settles the attempt (`job.retry_scheduled`, problem `job-stalled`) and starts the next one as a new task; a job that was still `QUEUED` when its worker died is retried in place within a few minutes. After the first case the dead attempt's row in `public.procrastinate_jobs` keeps status `doing` for good. It is inert and needs no action: it blocks no new dispatch, the job row names the new task, and nothing reads the old one. List such rows, as the database superuser, with `select t.id, t.task_name, t.attempts from public.procrastinate_jobs t where t.status = 'doing' and not exists (select 1 from erev.job j where j.procrastinate_job_id = t.id)`; a row that a running job still names is that job's live task, not a leftover. Do not edit or delete task rows while a worker runs.
- A failing handler is retried per its retry policy, after 30, 120 and then 600 seconds. After the last attempt the job is `FAILED` and `job.problem` holds the problem object; the log line `job.failed` names the job id, kind, attempt and error class, never the error message.
- A `RUNNING` job that has not updated its row for 10 minutes (no progress or heartbeat) and has no transaction open is stalled. The same minute sweeper counts it as a failed attempt: it goes back to `QUEUED` while its policy allows another attempt (log line `job.retry_scheduled`), otherwise it is `FAILED` with problem `job-stalled` and detail "no heartbeat for 10 minutes". A worker that dies mid-job therefore costs about 10 minutes before the retry: PostgreSQL ends the transaction a dead worker left open within about two minutes, whatever the network does — the statement it was in, at most 60 seconds, then 60 seconds idle (inside a dataset freeze the idle limit is `EREV_DATASET_FREEZE_IDLE_SECONDS`, 15 minutes by default).
- A job that is silent for 10 minutes while one of its transactions is open is passed over, not stopped: its worker is alive, and what that transaction writes is the job's (05 JOB-06). The sweeper says so every minute with the log line `job.sweep_passed_over` (info level): `job_id`, `job_kind`, `attempt` and `silent_seconds`, the time since the job's last heartbeat. Read it like this. One or two such lines for a job are a long transaction on a busy server; the line stops when the transaction commits, and the job goes on or ends. A job named minute after minute, with `silent_seconds` growing by 60, has a handler that works inside one transaction. Three things end that. Its own commit. PostgreSQL, when a statement runs longer than 60 seconds or the transaction is idle for 60 seconds (the dataset freeze's limit inside a freeze): the attempt then fails with a database error and is retried per its policy. Or you: find the transaction, as the database superuser, with `select l.pid, a.xact_start, a.state, left(a.query, 80) from pg_locks l join pg_stat_activity a on a.pid = l.pid where l.locktype = 'advisory' and l.mode = 'ShareLock' and l.granted and ((l.classid::bigint << 32) | l.objid::bigint) = hashtextextended('erev-job-unit:<job id>', 0)`, judge from `xact_start` and the statement whether it still does what the job is for, and end it with `select pg_terminate_backend(<pid>)`. Nothing of that transaction is kept, and the worker settles the attempt as a failed one — retried while its policy allows, otherwise `FAILED` with its notification. Do not edit the job's row. Nothing ends such a transaction by itself while it keeps sending statements, and no alert is raised for it: the log line is the signal.
- Long handlers heartbeat, so they are not taken for stalled: relays after each message, webhook deliveries after each delivery, chain verification after every 1,000 events or 30 seconds, retention after each chunk. A handler that is alive outside a transaction for 10 minutes without a heartbeat — a slow ledger pull, a fetch — is still stopped. Such an attempt keeps nothing from then on: its next heartbeat and its next unit of work are refused, the worker logs `job.attempt_lost` (warning) for it, and only the attempt whose Procrastinate task the job row names writes the result. What the stopped attempt had committed before stays, as for any failed attempt.
- A `QUEUED` job whose Procrastinate task ended without starting it (status `failed`, `cancelled` or `aborted`, for example after a database error before the job moved to `RUNNING`), or whose task is stuck in `doing` on a worker that stopped heartbeating 30 seconds ago, is recovered by the same minute sweeper. A failed task is replaced by a new dispatch of the next attempt after the kind's backoff; a stalled task is retried in place with Procrastinate's `retry_job_by_id`. After the last attempt the job is `FAILED` with problem `job-stalled` and detail "the worker task stopped before the job started". Periodic tasks count only jobs that are `RUNNING`, or `QUEUED` with a task still `todo` or `doing`, so daily chain verifications, retention sweeps, relays and webhook deliveries keep being deferred while such a job waits.
- Retry profiles (05 §5.6): `OUTBOX_RELAY` 8 attempts (30 s doubling to at most 15 minutes), `WEBHOOK_DELIVERY`, `EMAIL_DELIVERY` and `RETENTION_SWEEP` 5 attempts (30, 60, 120, 240 s), `AUDIT_CHAIN_VERIFY` and `PERIOD_OPEN_REDIRTY` 3 attempts; other kinds one attempt until their phase sets a profile.
- After the last attempt the person who started the job receives the notification "Job failed: <job label>" in the app and, by default, by email. A job that no person started — a periodic job of the scheduler, a job of an API client — raises the operator alert `JOB_FAILED` instead: the log line `operator_alert.raised` (warning level) with the tenant id, the job id, its kind, its queue, the attempt, the slug of its problem and the kind of its initiator, one line in the alert trail under `<EREV_RUN_DIR>/operator-alerts/` and, when `EREV_OPERATOR_ALERT_EMAIL` is set, an email to that address; a hosted deployment has an alert policy on the log line. Read the job with `GET /api/v1/jobs/<job id>` as a holder of `audit.read` in that workspace, fix the cause its `problem` names and start the operation again; a periodic job is deferred again at its next tick. A failed job whose record belongs to one legal entity — an upload, a contract, a journal run, a reconciliation, a sync run, a period's re-marking — also leaves the exception item `JOB_FAILED` in the queue of that entity. It is information and holds no close; it closes by itself when a later job of the same kind for the same record completes, and a holder of `exception.resolve` dismisses it with a comment when none will follow. A failed close-run job raises a close-cockpit blocker and notifies the entity's Controllers (see "Close runs").
- A job whose kind has no handler yet fails at once with the problem title "Job failed".

### Close runs

Runbook entry RB-07 for close runs (05 RCP-19, RCP-20, JOB-07; 04 T-CLS-01).

- A close run is one `CLOSE_RUN` job on queue `close` per start or resume. `GET /api/v1/close-runs/{id}` shows its fourteen steps with status, times and counts, the step it is at (`current_step_code`) and its newest job; `GET /api/v1/close-runs?entity=<code>&period=<key>` lists the runs of a period, newest first. One run per entity, book and period can be active (`PENDING`, `RUNNING`, `BLOCKED`): starting another answers the active one.
- The job has no automatic retry. When a step raises, or the worker dies and the job is dead-lettered as stalled, the run is `FAILED` at that step with the problem in `steps[].problem`, nothing of the step is kept (the contracts "Recompute changed contracts" had already recalculated stay recalculated), the initiator and the holders of `period.lock` for the entity receive "Job failed: Close run", and the exception queue shows one blocking item `CLOSE_RUN_FAILED` for the entity, book and period. Fix the cause, then `POST /api/v1/close-runs/{id}/resume` (permission `period.close`): the run continues at the failed step and the steps that had succeeded are not executed again. The item is settled when a close run of the period succeeds.
- `BLOCKED` means "Recompute changed contracts" left quarantined contracts: each has a blocking exception item `ENGINE_INVARIANT_VIOLATION` (or the engine's own code) naming the contract. Correct the contract and resume; or have the item waived (`exception.waive`, a second person) and resume — a waived contract is not recalculated again while nothing on it changes, and it keeps the gate "Contracts changed since the last close run" failing until it is corrected or that gate is waived.
- `POST /api/v1/close-runs/{id}/cancel` with a reason of at least 10 characters stops a running run after its current step; a run whose job has not started, and a blocked run, is cancelled at once. A cancelled or failed run does not prevent a new run for the period.
- While it waits for the child `CONTRACT_COMPUTE` jobs of "Recompute changed contracts" (queue `compute`, 250 contract groups per job) the close-run job holds one worker task. Children take no per-tenant job slot. A child that no worker has started within two polls (about 4 seconds) is computed by the close-run job itself, so a deployment whose worker tasks are all held by close runs still finishes; it is slower, not stuck. For a close of many entities at once give `compute` its own worker (`erev worker --queues compute`) or raise `EREV_WORKER_CONCURRENCY` above the number of close runs started together.
- The steps after "Recompute changed contracts" are executed in the order FX remeasurement, Release schedules, Contract balance reclassification, then as listed; the list on the screen keeps the documented order.
- The three period-end steps each compute every contract group of the entity once and post in one transaction per step: FX remeasurement and the reclassification as one posting of the entity, a release as one posting per contract group. They post the period-end amounts of the run's own period. Close the periods in order: when an earlier period still has period-end amounts no close run has posted, the run fails at the step with "<period name> has period-end amounts no close run has posted; run its close first." and posts nothing of that step — run the close of the period it names, then resume this run. Entries of an earlier period that cancel each other in every account role are not counted as unposted. "Release schedules" posts loss provisions and dated releases only — scheduled revenue is posted when a contract is calculated — so "0 postings, 0 lines" is the usual result. A contract group the engine refuses in one of these steps fails the run at that step and names the group and the engine's code (a closing rate that is not published yet, for instance): publish or correct, then resume.
- "Invariant checks" failing (`BLOCKED`, the step `FAILED` with "Entries do not balance") means the period's ledger lines do not sum to zero per currency. The database refuses an unbalanced posting when it is sealed, so this is a finding for engineering, not for the accountant: keep the run, do not lock, and escalate as SEV-2 with the run number.
- "Journal summarization" calculates one draft journal run for the period when the period has none, or when postings were sealed since its last run; otherwise it shows "0 batches". "Export", "Acknowledgement wait" and "Subledger to GL tie-out" only record what they find; approving, exporting and reconciling stay the accountant's actions, and a second close run afterwards records the full picture.
- "Dataset freeze" writes the twelve lock datasets as they stand when the step runs. The lock freezes again at the moment it is decided; a dataset that did not change in between is the same stored file. The "Lock" row turns Succeeded when the period is locked.
- The lock requires the period's close run: the gate "Close run completed" passes when the period's latest close run succeeded and no contract has a period-end amount of the period still to post since. It cannot be waived. "Close run not completed" — no run yet; "Close run <no> is <status>" — the latest run failed, is blocked, was cancelled or is still running: resume it or start a new one; "Close run out of date, run it again: <n> contracts" — contracts were recalculated after the run with something dated in the period or earlier (a late event, a correction): start a new run, which posts the difference. Work recorded for a later period does not put the run out of date. A contract whose period-end amount cannot be built at all is counted too; the new run then stops at the period-end step concerned and names the contract group and the reason — for example an account mapping without an account for a role the reclassification needs (`ACCOUNT_MAPPING_MISSING`): correct the cause, then resume the run. A rate dated on or before the period's last day that is replaced after the run, and a policy value of the kind set per period that comes into force after it and on or before the period's last day, put the run out of date as well (a policy value that comes into force after the period's last day belongs to a later period and asks for nothing): the gate reads "Close run out of date, run it again: exchange rates changed since it ran. A run posts nothing where the change moves nothing for this entity." (or "policies", or both) — start a new run; it posts the difference to the period-end amounts, or nothing. The rates and policies are the workspace's, so a correction for a currency this entity does not use asks for a run that posts nothing. The approval of the rate set version also marks the contracts its changed rates reach as changed (the gate "All contracts computed" counts them until they are recalculated): the new run recalculates them in its step "Recompute changed contracts" and posts revenue that was translated at a corrected average or spot rate, before its period-end steps; until then those amounts are as last calculated. A period that is already locked is not asked for a run. When the approval of a rate set version changes a rate dated in a period that is closed, the exception "FX rate changed after lock" (`FX_RATE_CHANGED_AFTER_LOCK`) is raised for each entity and book that closed the period, and the Revenue Accountants and the Controllers of the entity are told. It is an exception of the period the difference will post to — the next open period — and that period cannot be locked while it is open. Two ways out: reopen the closed period (the exception is then resolved by the system, and the period needs a new close run before its next lock), or request a waiver of the exception, which another person approves. What then remains of the difference is posted in the next open period. The contracts the changed rates reach are recalculated — by the next close run of the entity that contracts them, or by the next change to them — and what the rates change in the amounts of their events (revenue, the difference at a settlement) is posted with the closed period of each event as origin period; the out-of-period register lists it as "Fx republish", or with an event of the contract that was recorded first and carried it. The close run of the next open period posts what remains of a period-end remeasurement, as an amount of that period and without an origin period. Where nothing remains nothing is posted: a closing rate corrected in a period that is followed by another closed period moves an amount between the two closed periods, and for a balance that stayed open through both the next run posts that period's own remeasurement and no more. The exception names the rates and no amount. A permanently locked period, and a period behind a later closed one, cannot be reopened as they stand: the exception says so. An entity that does not use the currency gets the exception too; its waiver is the record that nothing moves. If the approval of a rate set version answers "Another change was in progress" after about ten seconds, a period was being locked or reopened at that moment, or a contract the changed rates reach was being calculated: nothing was saved; approve the version again. A close run that reaches such a contract while the approval is being saved leaves it out: the gate "All contracts computed" then counts it, and the next run recalculates it. From a run's first period-end step until the period is locked, each recalculation of a contract of that entity also evaluates the three period-end steps for it, without posting, so it takes about four times as long as usual; imports of many rows are best committed before the run or after the lock.
- A database that was seeded before the gate existed (Alembic revision 0111) enforces it — the lock is refused by name — but its checklist does not list the row until the workspace is seeded again. No workspace is deployed; a system gate added after a first deployment needs a seeding step of its own (known limitation CLOSE-GATE-SEED-1).

### Re-marking after a lock opened the next period

Locking a period opens the next one when it is still to come (PRD BR-CLS-03), and the contracts with an effect in the opened period are re-marked for the next recompute by a job the lock decision defers, kind `PERIOD_OPEN_REDIRTY` (05 SCH-06, §5.6: queue `close`, 3 attempts). A period opened from the screen or by the schedule is re-marked in the opening itself and has no such job.

A period whose gate "All contracts computed" reads "Contracts not re-marked since the period was opened" has a `PERIOD_OPEN_REDIRTY` job that has not succeeded: `GET /api/v1/jobs?kind=PERIOD_OPEN_REDIRTY` shows each attempt's job with its problem; the scheduler defers it again every 15 minutes (log `period_open_redirty.redeferred` with the period state and the count of failed jobs); nothing is posted and nothing is lost meanwhile, and the period cannot be locked until one job succeeds — remove the cause the problem names and wait for the next tick. That gate is not waivable while it reads so.

### Jobs API

- `GET /api/v1/jobs` lists the jobs the caller started; holders of `audit.read` for all entities see every job of the workspace. Filter with `kind`, `state`, `subject_type` and `subject_id` (repeat a parameter for several values). `GET /api/v1/jobs/{id}` returns state, progress, result link and problem; anyone else gets 404.
- `POST /api/v1/jobs/{id}/cancel` needs an `Idempotency-Key` and is open only to the person who started the job. A queued job is cancelled at once. A running job records the request and ends `CANCELLED` after its current chunk, keeping the counts of the chunks it finished. A finished job returns 409 `invalid-transition`. Cancelling writes no audit event.

### Retention

- Every day at 03:00 UTC the periodic task `idempotency_purge` defers one `RETENTION_SWEEP` job per ACTIVE workspace that has no sweep waiting or running. The sweep deletes idempotency records past their 7-day expiry, sessions that ended more than 30 days ago and password reset tokens past `expires_at`, at most 100 rows per transaction, and reports the three counts in `result.counts`.
- At 03:10 UTC `session_purge` deletes the expired sessions and reset tokens directly, so they expire even while no workspace is ACTIVE.
- A failed sweep is retried up to 5 attempts. Deleted rows are not audited; sign-in and reset evidence stays in `security_event`.

## Outbox and email

Email, webhook and journal export messages wait in `erev.outbox_message` until the worker relays them (05 ADP-30 to ADP-32).

- A command that enqueues a message defers one `OUTBOX_RELAY` job after it commits. Every minute the periodic task `outbox_sweeper` also defers a relay for each workspace that has due messages, or messages left in `DISPATCHING` for more than 15 minutes.
- A relay claims one message at a time, just before dispatching it: the claim sets `DISPATCHING` and stamps `updated_at`, and the result is recorded only while that stamp still holds. A message whose claim is more than 15 minutes old belongs to a relay that stopped; the next relay claims it again and sends it once. A relay handles at most 100 messages per run.
- A failed dispatch sets `FAILED`, counts the attempt and waits 30 s × 2^attempt, at most one hour. The tenth failure sets `DEAD`. `last_error` holds only the error class — for a database error that was mapped to a problem its slug, `lock-conflict` or `statement-timeout` — never the message.
- Tenant provisioning writes the invitation email. The sweeper relays it within a minute of provisioning.
- A database written by a build before the first release: until 04 T-INT-03 rev 1.151 the `EMAIL` row of a password-reset or invitation email kept the link with its token in `payload.link_path`; since then the row holds the place `{token}` and names the token in `payload.link_token`, and no table holds the token. No release wrote a row of the earlier form, so a first deployment has nothing to do. A database carried over from a pre-release build must not go into service with such rows: before the first start, delete its `EMAIL` rows that have a `link_path` and no `link_token` (`erev.outbox_message`, `topic = 'EMAIL'`; as `erev_owner` under the data-fix guard of 04 DB-01, because the table is append-only), then issue the open invitations again; an open reset link lapses within the hour.
- With `EREV_EMAIL_BACKEND=fake` (required in dev, test and e2e) each email is a file `.run/mail/<workspace code>/<UTC timestamp>-<reference>.eml`. Open the newest file of the workspace to find an invitation link. The directory is `mail/` under `EREV_RUN_DIR` of the process that relays, the worker. Under `production` the api and the worker refuse to start on `fake`: mail would be written to files nobody reads.
- With `EREV_EMAIL_BACKEND=smtp`, set `EREV_SMTP_HOST` and `EREV_SMTP_FROM`, and optionally `EREV_SMTP_PORT` (587), `EREV_SMTP_USERNAME` and `EREV_SMTP_PASSWORD`. STARTTLS and certificate verification are required. Outside `dev`, `test` and `e2e` the host must resolve only to public addresses (the destination guard of "Outbound webhooks"); a refused host fails the send before any connection, and the relay retries it as any other failure. The worker connects to the address it checked, names `EREV_SMTP_HOST` in the TLS handshake and verifies the certificate against it: a certificate for another name, or from an authority the image does not trust, fails the send in the handshake, before the sender, the recipient or the message is transmitted, and credentials are sent only inside the TLS session. A relay on a private or loopback address — one on the compose network included — is refused under `production` unless the operator opts in: `EREV_SMTP_PRIVATE_RELAY=true` also admits loopback (127.0.0.0/8, ::1) and private-use addresses (10/8, 172.16/12, 192.168/16, fc00::/7) for the SMTP host, and for nothing else — webhooks, integration connections and identity providers keep the public-address rule, and link-local addresses (the cloud metadata address among them) stay refused for the relay too. The opt-in relaxes neither STARTTLS nor certificate verification. A relay with a certificate of your own authority needs `EREV_SMTP_CA_FILE`, the path of a PEM file with that authority's certificate: the worker then verifies the relay against that file instead of the image's trust store. `erev doctor` prints `WARN email-backend` while the opt-in is on, and a bundle that cannot be read fails the check and stops the api and the worker at start. `production` requires this backend, with the host and the sender set ("Production checks", `email-backend`).

### Journal export messages

Approving a journal run writes one `JOURNAL_EXPORT` message per batch in the approving transaction. Its `dedupe_key` is the batch's external id `erev:<workspace code>:<run no>:<batch no>:<chunk no>` (05 ADP-30). Sandbox workspaces write none (ADP-34).

- The relay posts a batch through the adapter the batch was calculated for. `CSV` stores the export file and sets the batch `exported`. An adapter that answers with an ERP document id also records the acknowledgement and sets the batch `acknowledged`. The run follows once every batch has moved.
- The adapter and the connection of a run are fixed when the run is calculated: the one `ACTIVE` connection of adapter `NETSUITE`, `QUICKBOOKS_ONLINE` or `CSV_GL` with direction `OUTBOUND` or `BOTH` that covers the run's entity; none gives `CSV`. Two such connections refuse the calculation by name — disable all but one. A batch of NetSuite or QuickBooks Online is cut into chunks of at most `config.max_lines_per_chunk` lines (default 500 and 250); each chunk is a batch row with its own external id and message. To move a calculated run to another ledger, cancel it and calculate it again.
- The relay reads the batch's connection at each dispatch. A connection that is `DISABLED` or no longer exists fails the batch (`Permanent`) with that message and sends nothing: enable the connection, then retry the batch ("Dead letters of JOURNAL_EXPORT").
- A 429 or 503 that states `Retry-After` moves the next attempt to the later of the schedule's wait and the stated wait.
- What a batch states (05 ADP-10; ruling R-110). The CSV carries each line in the transaction currency and in the entity's functional currency (`functional_currency`, `debit_functional`, `credit_functional`; the manifest has `totals` and `totals_functional`). A batch sent through the NetSuite or QuickBooks Online adapter is one document in the entity's FUNCTIONAL currency with the functional amounts; the transaction currency and amounts of a foreign-currency batch go along as informational fields. For the operator of the ledger: the accounts eRev posts to carry these balances in the functional currency only; the transaction-currency detail stays in eRev; and the ledger must not revalue those accounts itself, because eRev's foreign-currency remeasurement (entry kind `FX_REMEASUREMENT`) is the only remeasurement of these balances. Where the ledger posts its own invoices to the contract liability account in the transaction currency (billing mode `ERP`), that account holds entries in two currencies: its functional total is the figure to reconcile, its transaction-currency balance is not meaningful. The NetSuite journal names custom fields — on a line `custcol_erev_je_no`, `custcol_erev_dimensions`, `custcol_erev_source`, `custcol_erev_txn_debit` and `custcol_erev_txn_credit`, on the entry `custbody_erev_txn_currency` — which the mock accepts without a definition and a NetSuite account would have to define; QuickBooks Online carries the transaction amount in the line's description. The limits of the two journal APIs behind this form (one currency and one exchange rate per document, one amount per line; 500 and 250 lines per document) are read from their documentation and not verified against a live system.
- A timeout, connection error, 429 or 5xx (`Transient`) sets the message `FAILED` and retries it 30 s × 2^(n − 1) after the n-th failure, at most 15 minutes later. The eighth failure sets `DEAD` (ADP-12). A retry first asks the adapter for the posting by external id, so a timeout after the ledger posted never posts the batch twice.
- The accounts of a batch must be active and apply to the batch's entity (an empty entity list applies to every entity). A validation failure such as an unknown account (`Permanent`) sets the message `DEAD` at once. The batch becomes `failed`, counts the attempt and keeps the adapter's message in `last_error`; the eighth `Transient` failure ends the same way.
- A `failed` batch carries a `posting_ack` of kind `REJECTED` with the adapter's message and an open exception item `JOURNAL_EXPORT_FAILED` (source `JOURNAL`); the exporter and the Controllers whose role covers the batch's entity are notified (`EXPORT_FAILED`; a Controller of other entities alone is not). The run is `failed` while no other batch of it is `exported`. A `failed` batch was never exported: it has no `exported_at` and no export file.
- The relay dispatches only batches that are `approved`, or `failed` and being retried, and it reads that state under the run's and the batch's row locks just before it calls the adapter. A repeated message or a repeated export command never posts a batch twice.
- A journal run is not cancelled while the relay holds the message of one of its batches (`DISPATCHING`): the cancel answers 409 `invalid-transition` and names the batch. This holds whatever the age of the claim. If the relay stopped while it held the message, the sweeper hands the message to the next relay 15 minutes after the claim, and that relay completes the export: a ledger that already holds the batch answers with its document, which is recorded as a `DUPLICATE` receipt, so nothing posts twice. The batch is then `exported`, `acknowledged` or `failed`, and the run is corrected by the means of that state. While no worker runs, such a run cannot be cancelled: the product cannot know what the ledger holds without asking it. Start a worker; do not change the message or the batch by hand.
- Nor is a journal run cancelled while the message of one of its batches is `FAILED` and due again: an attempt was made, and a timeout can follow the ledger's acceptance. The cancel answers 409 `invalid-transition`, "An export of this journal run is in progress: an attempt to send batch <external id> failed and it will be sent again. It cannot be cancelled until the batch has been sent or has failed." The next attempt asks the ledger for the posting first; the batch ends `exported` or `acknowledged` — the run is then past cancelling — or, after the eighth attempt, `failed`, and the cancel of the failed run asks the ledger (step 5 below). With a worker running the eight attempts take about 45 minutes, longer when the ledger states a wait. A message that is still `PENDING` was never sent and does not refuse the cancel.
- A journal run is neither calculated nor cancelled in a period that is `closed` or `permanently_locked`: `POST /api/v1/journal-runs` and the cancel answer 409 `period-closed` ("… A journal run cannot be calculated for a closed period.", "… A journal run of a closed period cannot be cancelled."), and a calculation that was accepted before the lock and runs after it ends `FAILED` with the same problem. The lock certified the period's journals; to change them, reopen the period. A cancel or a calculation that meets a lock decision in flight waits for it — beyond the lock timeout it answers 409 `lock-conflict` and is sent again.

### Dead letters of JOURNAL_EXPORT

A `DEAD` journal export message is a batch the adapter refused, or whose eighth attempt failed. Its batch is `failed`. The relay says so in the log once: the line `outbox.dispatch_failed` with `outcome` `DEAD` (an attempt that will be made again reads `FAILED`, a message that could not be settled `UNSETTLED`); a hosted deployment pages on that line (SLO-05).

1. Find them: `outbox_message` rows with `topic = 'JOURNAL_EXPORT'` and `status = 'DEAD'`, joined to `journal_batch` on `outbox_message_id`. The message's `last_error` is the error class — `Permanent` for a refusal, `Transient` for a ledger that did not answer, `Accepted` for a ledger that took the batch and did not show it when it was read back — or the slug of a problem (`lock-conflict`, `statement-timeout`); the batch's `last_error` is the adapter's message, or "eRev could not complete the export (<slug or class>); the ledger may hold the batch." when the dispatch ended with an error of eRev's own.
2. Fix the cause: map, activate or extend to the batch's entity the account the message names, or restore the adapter's connection. After a `Transient` dead letter, check in the ledger whether the external id was posted before you resend.
3. Retry: `POST /api/v1/journal-batches/<id>/retry` as a holder of `journal.export` — or, for every failed batch of a run at once, `POST /api/v1/journal-runs/<id>/export`, which takes each failed batch under the same rule and is refused whole (409, by the batch's name, nothing written) while one of them is being sent. It answers 202 with a `JOURNAL_EXPORT` job and writes a new message whose `dedupe_key` is the external id followed by `#<attempt count>`; the dead message stays `DEAD`. The batch keeps its external id and the retry asks the ledger for the posting first, so nothing posts twice. Once the adapter accepts the batch it is `exported` (or `acknowledged`, with the ledger's document id) and its exception item is resolved. While the batch's message is still `DISPATCHING` the retry answers 409, "Batch <external id> is being sent. …": a worker stopped after it recorded the batch `failed` and before it recorded the message `DEAD`. Wait: 15 minutes after the claim the sweeper hands the message to a relay, and that dispatch is the retry — it asks the ledger first. If an attempt of that dispatch fails and attempts remain, the message is `FAILED` and due again like any other; a retry then answers 202 and writes no second message — the message is the retry, and it is sent when it is due: the retry does not make it due earlier, because the wait a ledger stated is part of its schedule. The job of that retry says so in `result.waiting` — the batch and `next_attempt_at`.
4. A batch that failed with "Batch <external id> differs from what was calculated and approved: …" was changed after its approval: the lines the dispatch found are not the ones its stored count and totals — the figures the approver saw — describe (05 ADP-31, the recount). Nothing was sent and a retry is refused the same way. Treat it as a security event, not an export fault: find who wrote the line (the application writes journal lines only when a run is calculated; `journal_line.created_at` and the database's own logs), and do not edit the batch to make it pass.
5. A batch the ledger can never accept as generated has two more exits (04 T-SL-07 "The ways out of `failed`"). When NO batch of the run is `exported` or `acknowledged`: `POST /api/v1/journal-runs/<id>/cancel` with a reason, as a holder of `journal.run`. It answers 202 with a `JOURNAL_EXPORT` job that first asks the ledger for every failed batch by its external id. A batch the ledger holds after all is acknowledged with the ledger's document and the run is NOT cancelled (the job ends `SUCCEEDED_WITH_EXCEPTIONS`; read `result.refusal`). A ledger that cannot be reached changes nothing: the job tries again on the retry schedule and ends `FAILED` if it never answers — cancel again later. While a retry of one of the run's batches is still to be sent, or is being sent, the cancel answers 409: let the retry end first. Otherwise run and batches are `cancelled`; correct the cause (the mapping, the connection's `max_lines_per_chunk`, a subledger correction) and calculate the period again: the new run has new external ids and is approved again.
6. When part of the run IS in a ledger, the run is not cancelled (409, "… has a batch that a ledger holds or that was handed out …"). Hand the failed batch over instead: `POST /api/v1/journal-batches/<id>/hand-over` as a holder of `journal.export` (ERP adapters only). After the same question to the ledger the batch is `exported` with its file; download it, post it by hand in the ledger — put the batch's external id in the document's memo — and record the ledger's document with `POST …/acknowledge`. Until then the acknowledgement gate counts the batch. Wrong content in such a run is corrected in the subledger and posted by hand together with its correction: eRev does not net the two batches.
7. A connection that was deleted cannot be asked, so a failed run of that ledger is neither cancelled nor handed over: restore a connection first.
8. A batch that failed with "eRev could not complete the export (<slug or class>); the ledger may hold the batch." did not hear from the ledger: its dispatch ended with a database error or another error of eRev's own, possibly after the ledger accepted the chunk. Retry it (step 3): the retry asks the ledger first and records the document it finds. Every other exit asks the ledger too.
9. A message that stays `DISPATCHING` after its eighth attempt could not record its batch `failed` (log line `outbox.dead_hook_failed`): nothing is lost, the relay takes it again 15 minutes later. Look for what holds the run's rows — a long transaction, a lock — in `pg_stat_activity`.
10. The cancel of a failed run (step 5) and the hand-over (step 6) ask the ledger whether it holds the failed batch, and its "no" is only as good as the ledger's promptness. So both wait. After a dead letter that was not the ledger's refusal — `last_error` is not `Permanent` — they answer 409 for 15 minutes from the end of the last attempt, "The last attempt to send batch <external id> ended less than 15 minutes ago without the ledger's refusal, so the ledger may still take it. …", and name the minutes left. A retry is taken at once: it asks the ledger first. After a dead letter with `last_error` `Accepted` they answer 409 at any age, "The ledger accepted batch <external id> and does not show it yet. …": retry the batch — once the ledger shows the journal the retry records it and the batch is `acknowledged`; if the ledger refuses the chunk the batch dies of that refusal and both exits open. Look in the ledger for the external id meanwhile. The 15 minutes make a late acceptance unlikely to be missed, not impossible: a ledger that applies a request it never answered more than 15 minutes later is not seen by the exit that asks. Where a ledger is known to do that, do not cancel or hand over on eRev's question alone — look for the external id in the ledger first.

## Outbound webhooks

Workspaces subscribe URLs to `run.completed`, `import.committed`, `period.locked`, `journal_batch.exported`, `journal_batch.acknowledged` and `exception.raised` (03 REQ-PLT-034; 04 T-PLT-35, T-PLT-36; 05 NTR-10 to NTR-13). Emitted in this release: `journal_batch.exported` and `journal_batch.acknowledged`, in the transaction that writes the batch state, with `data` `{id, href, journal_run_id, journal_run_href}`. The other four kinds can be subscribed to and are not emitted yet (item WEBHOOK-EMIT-1).

- Holders of `webhook.manage` for all entities (Integration Admin) manage endpoints with `GET, POST /api/v1/webhook-endpoints` and `GET, PATCH /api/v1/webhook-endpoints/<id>` (`If-Match` required), and read the delivery log with `GET /api/v1/webhook-deliveries` (filters `status`, `webhook_endpoint_id`, `event_kind`; newest first). Endpoints are never deleted; `is_active false` stops their deliveries, and a delivery due for an inactive endpoint is `ABANDONED`.
- The create response shows the signing secret once. It is stored sealed under the key ring in `webhook_endpoint.secret_ciphertext` (KEY-08). Resending the create request with the same `Idempotency-Key` replays the stored response with `Idempotent-Replay: true` and `signing_secret` null, because the idempotency record never keeps the secret (D-80). A lost secret needs a new endpoint.
- Every delivery is an HTTP POST of `{id, kind, tenant_code, occurred_at, data}`, where `data` holds only resource ids and hrefs, with header `X-Erev-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 over "<t>." + body>`. Receivers recompute the HMAC over the raw body and reject timestamps older than 5 minutes.
- Deliveries are claimed one at a time, just before their POST: the claim sets `next_attempt_at` two minutes ahead and commits, and the worker then holds the row until the result is written. A second worker therefore never posts the same attempt, even when a POST outlives the claim. A delivery job handles at most 100 deliveries per run.
- The `WEBHOOK` outbox message makes the first attempt. A 2xx answer is `SUCCEEDED`; anything else, a timeout (10 s) or a redirect is `FAILED`, due again 30 s × 2^(n − 1) after the n-th failure, at most one hour later. Every minute the periodic task `webhook_delivery_due` defers one `WEBHOOK_DELIVERY` job per workspace with due deliveries. A delivery still failing at `abandon_at` (created + 24 hours) is `ABANDONED`. `last_error` holds `HTTP <status>`, the destination rule or the error class only.
- Destination guard (05 SAR-15; D-80): with `EREV_ENV=production` only https destinations whose host resolves only to global unicast addresses are called, and the worker connects to the address it checked. Refused: loopback, private, link-local (including 169.254.169.254), CGNAT, benchmarking (198.18.0.0/15), IETF protocol assignments (192.0.0.0/24), multicast, broadcast, reserved and IPv6 site-local addresses, and credentials in the URL. NAT64 (`64:ff9b::/96`), 6to4 (`2002::/16`), IPv4-mapped and IPv4-compatible addresses are judged by the IPv4 address they carry. `dev`, `test` and `e2e` also allow loopback addresses and http for the in-process mocks. The same guard covers identity provider requests and the SMTP host.

## API clients and access tokens

Integrations call the API as OAuth2 client-credentials API clients (03 REQ-PLT-033; 04 T-PLT-15, T-PLT-16, API-R-02, API-R-08; 05 SAR-28, THR-04; CTL-037).

- An API client is requested, approved by another person, and only then given its secret: its scopes are an access grant (03 REQ-PLT-033; supervisor ruling R-38 (iii)). A holder of `api_client.manage` (Tenant Admin) requests it with `POST /api/v1/api-clients` — `name`, `scopes`, the entities (`is_all_entities`, true by default, or `is_all_entities` false with `entity_codes`), and optionally `expires_at` (default 365 days) and `rate_limit_per_minute` (default 600) — after a TOTP verification at most five minutes old. The answer is 201 with `status` `PENDING_APPROVAL`, `client_secret` null and, where the caller may read the request, its `approval_request_id`. Another person who holds `access.approve` for the client's entities — for all entities when the client is for all — decides the request as a role assignment is decided: on the Approvals screen, or with `POST /api/v1/approvals/<request id>/approve` or `/reject`. The requester cannot decide it (403 `self-approval`). Only during setup is the request of the bootstrap Tenant Admin approved at once (rule `AUTO-BOOTSTRAP`), and only then does the creation itself answer `ACTIVE` with a secret.
- A client is in one of four states: `status` in `GET /api/v1/api-clients/<id>` and in `GET /api/v1/api-clients` (filter `status`), and the Status column of Settings, API clients and webhooks. `PENDING_APPROVAL` ("Pending approval"): the request waits for its decision, and the client has no secret and cannot authenticate — wait, ask a holder of `access.approve`, or withdraw the request (`POST /api/v1/approvals/<request id>/withdraw`, the requester only), which leaves the client `REJECTED`. `REJECTED` ("Rejected"): the request was rejected, withdrawn or voided; nothing changes that — request another client. `ACTIVE` ("Active"): approved; it authenticates once its first secret is issued (below) and until its `expires_at`, which no command moves — after it, request another client. `REVOKED` ("Revoked"): nothing changes that — request another client. On a client that is not `ACTIVE`, `rotate-secret` and `revoke` answer 409 `invalid-transition` with the sentence of its state: "This API client is waiting for approval.", "The request for this API client was not approved." or "This API client is revoked."
- The first secret: once the client is `ACTIVE`, a holder of `api_client.manage` who reaches it calls `POST /api/v1/api-clients/<id>/rotate-secret` (on the screen, Rotate secret) after a TOTP verification at most five minutes old, and is shown the secret once; the approval itself shows none. Until then `has_secret` is false. The same command replaces a secret later, and a lost secret needs it. `POST /api/v1/api-clients/<id>/revoke` needs a reason of at least 10 characters. Rotation and revocation revoke every open token of the client at once.
- Reach: a holder of `api_client.manage` lists, reads, gives a secret to and revokes only the clients whose every entity that permission covers — every client for a holder for all entities. A client beyond that is not listed and answers 404 `not-found`, as an id that names no client; `rotate-secret` and `revoke` on it also write a `DENIED` audit event under the client, which a holder of `audit.read` for all entities reads.
- No command changes a client's scopes, entities, expiry or rate limit: another set is another client and another request. Each command writes one audit event (`api_client.create`, `api_client.rotate_secret`, `api_client.revoke`), and the decision writes `api_client.activate` or `api_client.reject` with the id of the request.
- Scopes are permission codes. Approval permissions are refused with 422 `scope-not-allowed`, and trigger DB-12 refuses them on the row itself (`EREV-REF-002`). An API client never decides an approval: `POST /approvals/<id>/approve` answers 403 `forbidden`. Entities are named by their codes, within the requester's own scope for `api_client.manage`: a code that names no legal entity, or one outside that scope, is refused with 422 `validation-failed` ("Choose entities that exist in this workspace."), and a request that reaches beyond the requester's own scope is also recorded as a `DENIED` audit event.
- The client id (`erevc_<tenant hex>_…`) is in every answer. A secret is shown once, in the answer of the command that issued it; `api_client.secret_hash` keeps the argon2id hash. Resending the request with the same `Idempotency-Key` replays the stored response with `Idempotent-Replay: true` and `client_secret` null: the idempotency record never keeps the secret (D-80).
- A token comes from `POST /api/v1/oauth/token` with form `grant_type=client_credentials`, optionally `scope` (space-separated, a subset of the client's scopes), and HTTP Basic authentication with the client id and secret. The answer is `{access_token, token_type: "Bearer", expires_in: 3600, scope}` with `Cache-Control: no-store`. A wrong secret, an expired client, or a client that is not `ACTIVE` — waiting for approval, not approved, or revoked — gives 401 `unauthenticated`.
- Requests send `Authorization: Bearer erevt_<tenant hex>_…`. The workspace is the one in the token; permissions are the token's scopes; no CSRF token is needed. An expired or revoked token, or one of a client that is revoked or has expired, gives 401 `unauthenticated`. `api_token` keeps only the SHA-256 of each token, and the retention sweep deletes tokens 7 days after they expire.

## Tenant provisioning

Workspaces are created only by a platform operator (03 REQ-PLT-038; PRD BR-PLT-01; 04 §14.3, API-R-54; 05 SAR-24). There is no self-service sign-up, and sandboxes are never created here.

- **CLI.** `EREV_ENV=<dev|test|e2e> backend/.venv/bin/erev tenant create --code <code> --name "<display name>" --reporting-currency <ISO 4217> [--demo] --admin <email>`. `EREV_ENV` selects the database of a checkout; in a compose or hosted deployment the same command runs inside the api image as `/app/.venv/bin/erev tenant create …` under the container's `EREV_ENV` (see "Compose stack: start, first operator and first workspace"). On success it prints one JSON line, `{admin_membership_id, invitation_expires_at, tenant: {code, display_name, id, is_demo, kind, reporting_currency}}` with sorted keys, and exits 0. A problem goes to stderr as JSON and exits 1.
- **API.** `POST /api/v1/operator/tenants` with `{code, display_name, reporting_currency, is_demo, admin_email}` and an `Idempotency-Key`, from the cookie session of an operator (`erev operator create`) who has verified TOTP. Other users and bearer tokens get 403 `forbidden`; an unverified operator gets 403 `mfa-required`. The answer is 201 with the same document as the CLI and no `Location`. Requests are limited per source address, as sign-in is.
- **Validation.** The code has 3 to 40 lowercase letters, digits and single hyphens; the currency is an ISO 4217 code; the admin email is an address. A code already in use answers 422 `validation-failed` with `rule_id` `TENANT_CODE_EXISTS` and creates nothing. A repeated API request with the same key fails the same way, because the route keeps no idempotency record outside a tenant.
- **What one transaction creates.** The `production` tenant with `is_demo` from `--demo`, `setup_completed_at` empty and its audit key id `audit-hmac:<tenant id>:1`; the audit chain head; 13 numbering series; the ten system roles with their permissions; SoD-1 to SoD-7 published; one DEFAULT registry version per category (`registry_version.seed` by SYSTEM); rule set `AUTO-BOOTSTRAP`; the admin user when the email is unknown (no password until the invitation is accepted); the `INVITED` membership; the `tenant_admin` assignment approved by `AUTO-BOOTSTRAP` (`APR-000001`); and the invitation email in the outbox. A failure at any step leaves none of these rows.
- **Evidence.** `security_event` `PLATFORM_SCOPE_USED` names the tenant (and the operator for the API). Audit event 1 of the tenant chain is `tenant.provision` by principal kind `OPERATOR`, with `detail.channel` `CLI` and `detail.os_user`, or `API` and `detail.operator_user_id`.
- **Invitation.** The token travels only in the email link; neither the CLI nor the API prints it. The outbox sweeper relays the email within a minute once a worker runs; with `EREV_EMAIL_BACKEND=fake` the message lands under `.run/`. The invitation expires after 7 days.
- **Issuing the first invitation again.** Until the invited Tenant Admin accepts, nobody in the workspace can resend the invitation, and an operator cannot enter it. When the email was lost or the 7 days have passed, run `erev tenant resend-invitation --code <code> --admin <email>` (in a compose deployment inside the api container, as `tenant create`): a new link replaces the earlier one, which stops working at once, the 7 days start again and the email is queued again. It prints `{admin_membership_id, invitation_expires_at, tenant: {code, id}}` and never the token. Evidence: audit event `tenant_membership.resend_invitation` by principal kind `OPERATOR` with `detail.channel` `CLI` and `detail.os_user`, and a `PLATFORM_SCOPE_USED` security event under the same request id. It is refused, with nothing changed, for a code that names no production workspace or an email without a membership there (422 `validation-failed`), and for a membership that is not an open invitation an operator issued — an accepted or removed one, or an invitation a Tenant Admin sent (409 `invalid-transition`): once a Tenant Admin exists, invitations are resent from Users in the workspace.

### Sandbox copies on a hosted deployment

A sandbox copy creates a sandbox workspace, and every workspace needs its own audit key (05 KEY-05). Under `EREV_KEY_PROVIDER=local` (the compose stack) that key is derived from the audit master key, and the copy needs nothing else. Under `EREV_KEY_PROVIDER=gcp` the key is a Secret Manager secret, and only the identity of the `erev-tenant-provision` job may create one (`deploy/terraform/gcp/main.tf`: `provisioning_creator` and `provisioning_initializer`); a sandbox copy runs in the worker, whose identity reads tenant keys and creates none. **The first release offers no sandbox copies on a hosted deployment (supervisor ruling R-108 (b) (4); item OPS-SBX-KEY-1): a hosted sandbox copy fails closed** — the copy does not complete and the source workspace is not affected. The same holds for every job that makes a new sandbox workspace (05 SBX-02, SBX-07): hosted, sandbox copies, restores and empty resets are unavailable until the worker is given an authority that may create a tenant's audit key. Such a job ends `FAILED` with 412 `precondition-failed`, rule `SANDBOX_KEY_PROVISIONING_DENIED` — "A new sandbox workspace needs its own audit key, and this deployment's worker is not allowed to create one." — creates no tenant and no secret, and leaves nothing to clean up: the key is asked for inside the transaction that inserts the workspace's row. It is a known limitation of the hosted shape. Do not grant the worker's service account a Secret Manager role by hand to get past it: the separation is the control. The design for the release that offers hosted copies — the worker creates a sandbox workspace's key under a sandbox-only name prefix — is recorded in `docs/reviews/loop/sprint/OPS.md`, section 17. Not verifiable without a deployment.

## Operator support access

Platform operators read a workspace only under a support grant that a Tenant Admin approves (03 REQ-PLT-036; 04 T-PLT-33; 05 SAR-29, TB-7, THR-20, SCH-15; CTL-035). There is no standing operator access.

| Step | Command or route | Evidence |
|---|---|---|
| Create an operator | `backend/.venv/bin/erev operator create --email <email> --name "<display name>"` reads the password twice from a hidden prompt and prints one JSON line without the password. A used email exits 1. In a compose deployment the command runs in the api container (`docker compose … exec api /app/.venv/bin/erev operator create …`; see "Compose stack: start, first operator and first workspace"). | `app_user.is_operator`; `security_event` `PLATFORM_SCOPE_USED` with `detail.command` `operator.create` |
| Request access | `erev support-grant request --tenant <code> --operator <email> --reason "<text>" [--ticket <ref>] --from <RFC 3339> --to <RFC 3339>`. The reason needs 10 characters; the window ends after it starts, in the future, at most 72 hours later. A Tenant Admin of all entities can record the same request with `POST /api/v1/support-grants`. | `support_grant` REQUESTED; approval request `SUPPORT_GRANT` routed to `support_grant.approve`; notification "Support access requested" for every Tenant Admin of all entities (a Tenant Admin of named entities is neither told nor asked); audit `support_grant.request` |
| Approve | Another holder of `support_grant.approve` for all entities decides the request in the approval inbox. | `support_grant.approve`; `approved_at` |
| Open the workspace | The operator signs in, verifies TOTP, and calls `POST /api/v1/session/tenant`. Without an approved grant in force the workspace answers 404; an unverified session answers 403 `mfa-required`. A session that ended after the request was authenticated — signed out or revoked meanwhile — answers 401 `unauthenticated` ("Sign in to continue.") and opens nothing, as on every route: sign in again and repeat the call. | `user_session.operator_support_grant_id`; `TENANT_SELECTED` with `detail.support_grant_id`; audit `support_grant.open_session` |
| Read | The operator holds `contract.read`, `ssp.read`, `config.read` and `audit.read`. Every command answers 403 `forbidden`. | audit `support_grant.access` per request and `DENIED` events, each with `support_grant_id` |
| Revoke | `POST /api/v1/support-grants/<id>/revoke` with a reason of at least 10 characters, for an approved grant. The operator's sessions end at once. | audit `support_grant.revoke`; `end_reason` `REVOKED` |
| Expiry | The worker task `erev.support_grant_expiry` runs every 10 minutes and sets approved grants past `valid_to` to EXPIRED. Each operator request also checks the grant, so access stops at `valid_to` even when the worker is down. | audit `support_grant.expire` by SYSTEM; `end_reason` `REVOKED` |

- Filter the tenant audit log by `support_grant_id` to see everything an operator did under one grant.
- An operator account is a normal sign-in identity: reset its MFA or suspend it like any user, and its grants stop working with its sessions.

## Identity providers (OIDC sign-in)

Users may sign in through an OIDC identity provider (03 REQ-PLT-006; 04 T-PLT-03; 05 SAR-27, THR-05). Providers are global and have no route: only the command line writes them.

| Step | Command or route | Evidence |
|---|---|---|
| List the providers | `backend/.venv/bin/erev idp list` connects as `erev_app` — it needs no owner URL; in a compose deployment it runs in the api container (`docker compose … exec api /app/.venv/bin/erev idp list`) — and prints one JSON line, `providers`: every provider with its `code`, `kind`, `display_name`, `issuer_url`, `email_domains` and `is_enabled`, ordered by code. The commands below take the `code` of an `oidc` provider and name none when they refuse an unknown one: read it here. | none: the command reads only, writes no row and leaves no event |
| Add a provider | `backend/.venv/bin/erev idp create --code <code> --kind oidc --name "<name on the sign-in page>" --issuer-url <issuer> --client-id <client id> --email-domain <domain> [--email-domain <domain> …] [--client-secret-ref <secret store reference>]` connects as `erev_owner` and prints one JSON line (in a compose deployment only the `migrate` service holds the owner URL: `docker compose … run --rm migrate idp create …`). The code is 1 to 63 lower-case letters, digits, hyphens or underscores. Under `EREV_ENV=production` the issuer must be https on a host that is not loopback; `dev`, `test` and `e2e` also accept http on a loopback host for the mock IdP. `--email-domain` names the email domains the provider is authoritative for — 1 to 20 host names, stored in lower case; the provider signs in no email of another domain, and a provider without a domain signs nobody in — so does one registered before revision 0092, whose list is empty, until `erev idp domains --add` binds it to one. An invalid issuer, `--kind saml`, a used code and invalid domains exit 1 with rule `T-PLT-03`. | `identity_provider` row with `email_domains`; `security_event` `PLATFORM_SCOPE_USED` with `detail.command` `idp.create` |
| Invite an identity | `backend/.venv/bin/erev idp invite --code <code> --email <email>` connects as `erev_owner` and names the provider on the existing identity with that email. Only an invited identity signs in through a provider. Refused with exit 1 and rule `T-PLT-03`: an unknown provider, an email outside the provider's domains, no identity with that email, a platform operator, an identity that belongs to another provider. Inviting twice changes nothing. | `app_user.identity_provider_id`; `security_event` `PLATFORM_SCOPE_USED` on the identity with `detail.command` `idp.invite` |
| Change a provider's domains | `backend/.venv/bin/erev idp domains --code <code> [--add <domain> …] [--remove <domain> …]` connects as `erev_owner` (in a compose deployment `docker compose … run --rm migrate idp domains …`) and prints one JSON line: the provider's domains after the change, `added`, `removed` and `identities_outside`. The provider keeps 1 to 20 domains; the change holds from the next sign-in. `identities_outside` counts the identities invited for the provider whose email is outside its domains now: they are no longer signed in through the provider and stay invited. Refused with exit 1 and rule `T-PLT-03`: an unknown provider, no domain named, a domain that is no lower-case host name or is named twice, one domain added and removed, the last domain removed, more than twenty. Adding a domain that is bound or removing one that is not changes nothing. | `identity_provider.email_domains`; `security_event` `PLATFORM_SCOPE_USED` with `detail.command` `idp.domains` |
| Take a provider out of sign-in | `backend/.venv/bin/erev idp disable --code <code>` connects as `erev_owner` (in a compose deployment `docker compose … run --rm migrate idp disable …`) and prints one JSON line: `provider`, `is_enabled` and `changed`; `erev idp enable --code <code>` puts the provider back. From the next request on the sign-in page does not offer a disabled provider, its start route answers 404 `not-found`, and its callback answers 401 `unauthenticated` without sending anything to the provider: a sign-in that was under way does not complete — the callback reads the provider again in the transaction that opens the session, so one that was already past its first check is refused as well, with `LOGIN_FAILED` on the identity. Nothing else changes. The provider's identities stay invited and linked and sign in with their passwords, the other `idp` commands work on a disabled provider, and a session that was opened through it stays open until it ends or expires — up to twelve hours — unless `erev idp end-sessions` ends it (the next row). Refused with exit 1 and rule `T-PLT-03`: an unknown provider. Disabling a disabled provider or enabling an enabled one changes nothing. | `identity_provider.is_enabled`; `security_event` `PLATFORM_SCOPE_USED` with `detail.command` `idp.disable` or `idp.enable` and `detail.changed`; `LOGIN_FAILED` with `detail.reason` `provider_disabled` for each callback refused |
| End the sessions of a disabled provider | `backend/.venv/bin/erev idp end-sessions --code <code>` connects as `erev_app` — it needs no owner URL; in a compose deployment it runs in the api container (`docker compose … exec api /app/.venv/bin/erev idp end-sessions --code <code>`) — and prints one JSON line: `provider`, `identities` (how many had an open session through the provider) and `sessions_ended`. Every session that is open and was opened through the provider ends at once: its next request answers 401 `unauthenticated`, and the sign-in page no longer offers the provider. A session the same person opened with a password stays. Refused with exit 1 and rule `T-PLT-03`: an unknown provider, and a provider that is enabled — disable it first, or the next sign-in opens the ended sessions again. A second run ends nothing and is answered as done. | `user_session.ended_at` with `end_reason` `REVOKED`; `security_event` `PLATFORM_SCOPE_USED` with `detail.command` `idp.end-sessions`, `detail.identities` and `detail.sessions_ended` |
| A provider that can no longer be trusted | Disable it, then end its sessions: the two commands above, in that order. Ending a session undoes nothing its holder did, so read three things for the time in doubt. (1) Who signed in through the provider: `security_event` `LOGIN_SUCCEEDED` with `detail.provider`. (2) A second factor one of those identities enrolled in that time: `MFA_ENROLLED`. A session opened through a provider may enrol the identity's first factor; it cannot set or change a password, which asks for the current one. A workspace administrator resets such a factor ("Reset MFA", which ends the identity's sessions as well). (3) What those identities did in their workspaces: each workspace's audit log by actor (`GET /api/v1/audit-events?actor_id=<user id>&from=<time>`). API clients and their secrets, invitations, role assignments, webhook endpoints and connections outlive a session; the workspace's administrators revoke what they did not make. Put the provider back with `erev idp enable` when it is trusted again. | the `security_event` rows and the audit events named in the step |
| Register eRev at the provider | Redirect URI `<EREV_PUBLIC_ORIGIN>/api/v1/session/oidc/<code>/callback`; scopes `openid email profile`; PKCE S256. A confidential client's secret lives in the secret store under the reference, never in the database. | provider configuration |
| Sign in | `GET /api/v1/session` lists enabled providers in `capabilities.identity_providers`; `GET /api/v1/session/oidc/<code>/start` redirects to the provider, and the callback opens the session and redirects to `/sign-in`. | `user_session.auth_method` `oidc`; `LOGIN_SUCCEEDED` with `detail.provider` |
| First sign-in | Links the ACTIVE identity that was invited for the provider and has the same verified email, and records the provider's subject for it; every later sign-in must present that subject. The email alone links nobody. The IdP never creates a user and never grants a role. | `app_user.identity_provider_subject`; `OIDC_LINKED` once |
| Refusal | An unknown or unverified email, an email of a domain the provider is not bound to, an identity that was not invited for the provider or belongs to another, a subject other than the linked one, a changed `state`, another `nonce`, or an invalid signature, issuer, audience or expiry answers 401 `unauthenticated`; so does the callback of a provider the operator disabled. | `LOGIN_FAILED` with `detail.reason` (`email_domain_not_bound`, `not_invited_for_provider`, `linked_to_another_provider`, `subject_mismatch`, `subject_linked_to_another_identity`, `provider_disabled`, …) |
| Provider requests | Discovery, token and JWKS requests pass the destination guard of "Outbound webhooks" and go to the checked address with SNI set to the host. A discovery document naming a private, link-local or other refused endpoint fails the sign-in before anything is sent there. | `LOGIN_FAILED` with `detail.reason` `provider_request_failed` |

- Local development: provider `mock-oidc` with issuer `http://127.0.0.1:8190/api/v1/__mocks__/oidc` and client id `erev-local` uses the in-process mock IdP, which signs in the fixture user named by `login_hint` (`backend/erev_api/adapters/mocks/fixtures/oidc/users.json`). The mocks mount only under `EREV_ENV` `dev`, `test` and `e2e`; `POST /api/v1/__mocks__/__admin/faults` `{route, kind, count}` injects faults and `POST /api/v1/__mocks__/__admin/reset` restores the seeded state.

## Audit log and hash chain

Operational behaviour of the tenant audit log (03 REQ-PLT-018, REQ-PLT-019; 04 T-PLT-19, T-PLT-22, DB-01, DB-09; dev-guide §5.5).

| Behaviour | Rule | Evidence |
|---|---|---|
| Append-only | `erev_app` holds `SELECT` and `INSERT` on `audit_event` and no privilege on its partitions. UPDATE, DELETE and TRUNCATE raise `EREV-IMM-001` for every other role, except `erev_owner` with `app.data_fix_ticket` set. | grants; `tg_audit_event__immutable`, `tg_audit_event__truncate` and one TRUNCATE trigger per partition |
| Chain | Every event stores `hmac` = HMAC-SHA256 with the tenant key `audit-hmac:<tenant id>:1` over the previous `hmac` and the canonical event. A unit of work appends its events at commit, after its other writes, under the `audit_chain_head` row lock. | `audit_event.chain_seq`, `prev_hmac`, `hmac`, `hmac_key_id` |
| Continuity | An insert whose `chain_seq` is not the head plus one, or whose `prev_hmac` differs from the head, is refused with `EREV-AUD-001` (500 `ledger-integrity`). | `tg_audit_event__chain` |
| Denied commands | A refused command writes its `DENIED` event in its own transaction, so the event survives the command's rollback. | `audit_event.outcome` `DENIED` |
| Partitions | One partition per UTC month from 2018-01 to 2032-12, plus `audit_event_pdefault`. | `pg_partition_tree('erev.audit_event')` |

- `erev_api.audit.verify.verify_tenant_chain` recomputes every HMAC of a tenant in sequence order. A `FAIL` names the first sequence whose position, previous HMAC or content does not verify; no event after it is trusted.
- The tenant keys derive from `EREV_AUDIT_HMAC_MASTER_KEY`. A different master key makes every chain fail verification, so a restore needs the `.env` saved with the backup (DG-MK-backup).
- `erev_owner` is subject to forced row-level security without a policy of its own, so it sees no audit rows. A provider data fix therefore runs `ALTER TABLE erev.audit_event NO FORCE ROW LEVEL SECURITY`, the change and `ALTER TABLE erev.audit_event FORCE ROW LEVEL SECURITY` in one transaction with the ticket set. Any change to an audit event makes verification fail from that sequence, which is the intended evidence of the change.

### Chain verification

- Every day at 02:00 UTC the periodic task `audit_chain_verify_all` defers one `AUDIT_CHAIN_VERIFY` job per ACTIVE workspace that has no verification waiting or running. The job recomputes the whole chain and writes one `audit_chain_verification` row: the trigger (`SCHEDULED` or `ON_DEMAND`), the sequence range, the events checked, the result and, on failure, the first failing sequence with its reason. A failed job is retried up to 3 attempts.
- A `PASS` also stores the digest file `chain_digest.json` (purpose `AUDIT_DIGEST`) holding `tenant_id`, `last_chain_seq`, `last_hmac`, `hmac_key_id`, `events_checked` and `verified_at`. Keep the digests outside the database; hosted deployments copy them to the digest bucket (05 SAR-31). A `FAIL` stores no digest, because no event from the first failing sequence on is trusted.
- A verification is anchored twice (D-80). It reads `audit_chain_head` before the events and fails with "the chain ends before the head" when the last event checked is not the head's position and HMAC, so deleting the newest events cannot pass. It also fails with "a verified event is missing or changed" when the event at the latest earlier `PASS` row's `to_chain_seq` is gone or no longer carries that row's `digest_last_hmac`, which reveals a deletion hidden by rewinding the head.
- `tg_audit_chain_head__guard` refuses with `EREV-AUD-001` any update of `audit_chain_head` that does not come from appending an event, or that does not advance `last_chain_seq` by exactly one. Only the table owner can disable the trigger; a provider data fix must not move the head, and a moved head is detected by the next verification.
- A `FAIL` ends the job `SUCCEEDED_WITH_EXCEPTIONS` and notifies every Tenant Admin and Controller who holds the role for all entities, in the app and by email ("Audit chain verification failed"); nobody can turn this notification off. The chain is the workspace's own, so a holder of either role for named entities is not told; a workspace in which nobody holds either role for all entities has no reader of the notice, and the operator alert `AUDIT_CHAIN_VERIFICATION_FAILED` is raised all the same (PRD NTF-09). Handle it as a SEV-1 incident (05 RB-08): compare the failing event with the last digest, look for `erev_owner` data-fix tickets, and leave the chain unchanged. The close-cockpit exception item follows once the exception queue exists.
- At 02:30 UTC `security_chain_verify` verifies the global `security_event` chain. The worker logs `security_chain.verified` with `result`, `events_checked` and `last_chain_seq`; a failure logs at level error and needs the same incident response.
- Holders of `audit.read` for all entities read the events with `GET /api/v1/audit-events` (filters `object_type`, `object_id`, `actor_id`, `action`, `from` inclusive and `to` exclusive; newest first) and start a verification with `POST /api/v1/audit-events/verify`, which returns 202 with the job and `Location: /api/v1/jobs/<id>`; a holder for named entities is answered 403 on both. Any holder of `audit.read` reads the verifications with `GET /api/v1/audit-events/verifications`.

## Chain verification failure response

Runbook entry RB-08 (05 §7.6 SEV-1; SCH-01, SCH-02, SLO-06; 04 DB-01, DB-09; SAR-30, SAR-31). An audit or ledger chain that does not verify, a security chain that does not verify or a `REPLAY_VERIFY` mismatch under the same engine version is a SEV-1: acknowledge within 15 minutes and tell the affected Tenant Admins within 24 hours of confirmation.

1. Leave the chain as it is. No data fix, no re-run of the verification with another key, no disabled trigger. Rows could change while a trigger was off, so a disabled trigger is itself this incident.
2. Preserve the evidence first: `make backup` (its digests document records the failing verification and still dumps everything), the worker log lines `security_chain.verified` and `job.failed`, and hosted the pgAudit DDL and role log of the window (SAR-30).
3. Locate the break: `erev verify --all-tenants` prints `FAIL <workspace> audit-chain` or `FAIL <workspace> ledger <book>` with the first failing sequence and the reason (`prev_hmac differs`, `hmac does not match the event content`, `chain_seq is not contiguous`, `the chain ends before the head`, `a verified event is missing or changed`, `seal_sha256 does not match the posting content`); the same sits in `audit_chain_verification.first_failure_seq` and `failure_detail`. A `FAIL <workspace> files` whose entry in the verification document (`tenants[].files.entries`) has the status `foreign_storage_key` is no chain break: the row names the object of another workspace than its own or its sandbox's source, the application refuses to open it, and how the row came to be is what to find (RB-10).
4. Compare with the last digest: `tenants[].digest.last_chain_seq` and `last_hmac` in the verification document, and hosted the write-once copy in the digest bucket (RB-13). A failure before the digest's sequence means an event that already verified was changed or removed; after it, the newest events are affected.
5. Look for who could have written: sessions of `erev_owner` (RB-11), DDL and role changes in the pgAudit log, and `app.data_fix_ticket` settings (none exist in 1.0, so any occurrence is unexplained).
6. Decide the recovery with the incident lead: a restore by RB-04 at the last instant every chain verified, or an accepted, documented break with the failing event kept as evidence. Never rewrite the chain.
7. Post-incident review within 5 business days: timeline, root cause, the controls affected (CTL-038, CTL-039, CTL-047), actions (RB-10).

The daily audit verification notifies every Tenant Admin and Controller who holds the role for all entities, in the app and by email ("Audit chain verification failed"; nobody can turn it off). The security chain verification raises an operator alert only; the incident channel (UI-9) is paged from the log line `operator_alert.raised` of either failure — kind `AUDIT_CHAIN_VERIFICATION_FAILED` or `SECURITY_CHAIN_VERIFICATION_FAILED` (SLO-06).

## Replay verification mismatch

Runbook entry RB-09 (05 §3.11 RCP-28, RCP-29; §7.8 REL-06; REQ-OPS-011). `REPLAY_VERIFY` recomputes a stored computation from its pinned inputs and compares `output_sha256`; the job kind is registered and its handler and the `UPGRADE_VALIDATE` report are built by SOP-3. Until then the procedure below is executed with the engine's answer-key and golden gates (`make answer-keys`, `make parity`) against the release in question.

- A mismatch under the same `engine_version` is an integrity incident: handle it as RB-08 (SEV-1), preserve the computation's inputs and outputs, and do not post from the affected group until the cause is known.
- A mismatch after an engine upgrade is expected input to RB-16: MINOR releases fail on any difference; MAJOR releases produce the `UPGRADE_VALIDATE` report and need tenant approval before true-ups post.
- Record: the `contract_computation` id, `engine_version` before and after, the stored and recomputed `output_sha256`, and the release manifest of both builds.

## Incident handling and break-glass access

Runbook entry RB-10 (05 §7.6; PRV-12; TB-7; THR-20; SAR-30). The severity decides the clock.

| Severity | Definition | Examples | Acknowledge | Tenant communication |
|---|---|---|---|---|
| SEV-1 | Confidentiality or integrity of accounting evidence at risk, or total outage | Cross-tenant exposure; audit or ledger chain verification failure; `REPLAY_VERIFY` mismatch under the same engine version; duplicate ERP postings across tenants; key compromise | 15 minutes | Affected Tenant Admins within 24 hours of confirmation (PRV-12) |
| SEV-2 | A control fails for one or more tenants, or a core flow is unavailable | Close runs failing; export relay dead-lettering; RLS lint failure on a deployed build; restore required | 1 hour | Within 1 business day |
| SEV-3 | Degraded performance or a non-core feature unavailable | SLO-02 breach; AI provider errors; webhook delivery failures | 1 business day | Status note |
| SEV-4 | Cosmetic or single-user issue | UI defect | Backlog | None |

- Declare: post in the incident channel `<incident channel>` (UI-9) with the severity, the incident lead and the communications owner; open the incident record with the start time. Evidence is preserved before remediation: database snapshot or `make backup`, logs, `security_event` and `audit_event` exports.
- Remediate through application commands only. There is no production data-fix path in 1.0 (REQ-OPS-014 later; REL-07): no `UPDATE`, `DELETE` or `ALTER` against production data outside a migration of a released build.
- Break-glass database access is the exception for a SEV-1 or SEV-2 that cannot be handled through the application. It is never standing (TB-7): the request names the incident, the statements to run, the duration (at most 4 hours) and two approvers `<break-glass approver 1>` and `<break-glass approver 2>` (UI-10), who approve in the incident channel before the credential is released. The access uses the pipeline's `erev_owner` credential version (RB-11), every statement is copied into the incident record, pgAudit keeps the DDL and role log (SAR-30), the session is reviewed by the second approver afterwards, and the credential is rotated as soon as the access ends (KEY-06). Read access to tenant data for support goes through an approved support grant, never through break-glass.
- Personal data: a confirmed breach in a hosted deployment is notified to the affected tenants within 24 hours of confirmation so that they can meet their own 72-hour duty (GDPR Art. 33; PRV-12).
- Post-incident review within 5 business days: timeline, root cause, control impact by CTL id, actions with owners and dates, and the evidence retained. The review is stored with the incident record.

## erev_owner holders and the pipeline identity

Runbook entry RB-11 (05 TB-7, THR-09, THR-20; CMP-09; DPL-33; dev-guide DG-ENV-12; ITGC guide "Database roles and prerequisites"). `erev_owner` owns the schema, runs migrations and can disable the immutability triggers; whoever holds it can rewrite evidence, so nobody holds it standing.

| Deployment | Holder of `erev_owner` | Holder of `erev_app` | Standing human write access |
|---|---|---|---|
| Local development | The developer's own `.env` (mode 0600) against a database only that checkout uses (`erev`, or `erev_rv_<lane>` in a review worktree) | The same `.env` | The developer, on development data only |
| Hosted staging and production | The `erev-migrate` service account through the secret `erev-db-owner-url`, executed by the `erev-migrate` Cloud Run job (CMP-09) that the release pipeline starts; `<pipeline identity>` and `<erev_owner credential holders>` (UI-10) | The `erev-api` and `erev-worker` service accounts through `erev-db-app-url` | None. Operators read tenant data only under a support grant (REQ-PLT-036); writes happen only through break-glass (RB-10) |

### The backup role and the restore-target admin

Two further database identities exist beside `erev_owner` and `erev_app`, neither held by the api, the worker or a human as standing access:

| Role | Attributes | Where | Holder |
|---|---|---|---|
| `erev_backup` (`EREV_BACKUP_URL`) | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS`; read-only through `GRANT pg_read_all_data TO erev_backup` (which grants reads, not `BYPASSRLS`); `CONNECT` on the database | Recovery provider `NATIVE` only (self-hosted and dev databases), for `make backup` (RB-04). Provisionable where the provisioner is a superuser or already holds `BYPASSRLS`; on Cloud SQL that path is unestablished (no superuser, no documented customer grant), so hosted deployments have no `erev_backup`; P3b's Terraform user stays disabled by default (`backup_user_enabled = false`) | The backup operator (`<backup retention owner>`, UI-10) |
| `erev_restore_admin` (`EREV_RESTORE_ADMIN_URL`) | `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS` and membership of `erev_owner` (`GRANT erev_owner TO erev_restore_admin`), so restored objects belong to `erev_owner`; or the isolated server's superuser | The isolated `erev_rv_*` database of a `NATIVE` restore drill or recovery clone only, never a production database and never Cloud SQL (the hosted clone is loaded by Cloud SQL itself and verified under `erev_owner` and `erev_app`) | Whoever runs `make restore-verify` (RB-06); the lane drill used `erev_restore_admin` on a throwaway server |

Self-hosted provisioning (run once by the database administrator as a superuser or as a role that already holds `BYPASSRLS`, never by the application):

```sql
CREATE ROLE erev_backup WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD '<…>';
GRANT pg_read_all_data TO erev_backup;
GRANT CONNECT ON DATABASE erev TO erev_backup;
CREATE ROLE erev_restore_admin WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD '<…>';
GRANT erev_owner TO erev_restore_admin;
-- the isolated clone of a restore drill or recovery (RB-04), empty and owned by erev_owner
CREATE DATABASE erev_rv_<name> WITH OWNER erev_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE erev_rv_<name> FROM PUBLIC;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev_rv_<name> TO erev_owner;
GRANT CONNECT, TEMPORARY ON DATABASE erev_rv_<name> TO erev_app;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev_rv_<name> TO erev_restore_admin;
```

`BYPASSRLS` is what lets `pg_dump` read every tenant's rows (04 DB-14 bars `erev_owner` and `erev_app`), and `pg_read_all_data` keeps the role from writing anything. The credential lives with the backup operator only; `scripts/check_env.py --db` confirms its presence and shape without printing it.

Checks, run at every access review and after every incident:

```sql
SELECT usename, application_name, client_addr, backend_start
FROM pg_stat_activity WHERE usename = 'erev_owner';
```

Expected: no rows outside a running migration job or an approved break-glass window. `erev doctor` confirms that `erev_app` has neither `SUPERUSER` nor `BYPASSRLS` (`OK app-role`), and the role guard refuses any process whose owner connection is a superuser (DG-ENV-12). Hosted, the IAM bindings of the two URL secrets are reviewed quarterly:

```sh
gcloud secrets get-iam-policy erev-db-owner-url
gcloud secrets get-iam-policy erev-db-app-url
```

Expected: `roles/secretmanager.secretAccessor` on `erev-db-owner-url` for the `erev-migrate` service account only, and on `erev-db-app-url` for `erev-api` and `erev-worker` only. The backup identity of RB-04 (`BYPASSRLS`) is a third credential, held by the backup operator alone and never by the api or worker.

### Cloud SQL role attributes at first rollout

Cloud SQL creates `erev_owner` and `erev_app` (Terraform `google_sql_user`, `deploy/terraform/gcp/cloud_sql.tf`) as members of `cloudsqlsuperuser`, and Terraform cannot set the attributes the compose init script gives the same roles (`deploy/compose/initdb/01-roles.sql`: `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`; `CREATE` on the database for `erev_owner` only). Ruling of the merged lane P3 (main `b7f03fd`): the hardening is applied by the first `erev-migrate` job run and documented here. The application itself never holds a role statement (DG-ENV-14), so the first rollout runs these statements once, as the pipeline identity with the instance's admin user, immediately before the first `erev-migrate` job:

```sql
ALTER ROLE erev_owner WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE erev_app   WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE cloudsqlsuperuser FROM erev_owner, erev_app;
ALTER DATABASE erev OWNER TO erev_owner;
REVOKE ALL ON DATABASE erev FROM PUBLIC;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev TO erev_owner;
GRANT CONNECT, TEMPORARY ON DATABASE erev TO erev_app;
```

Expected afterwards, from any connection:

```sql
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
FROM pg_roles WHERE rolname IN ('erev_owner', 'erev_app');
```

Both rows show `f` in every attribute column, and the first `erev-migrate` run then passes the role guard (`erev_owner` without `SUPERUSER`, DG-ENV-12) and `erev doctor` prints `OK app-role: erev_app has neither SUPERUSER nor BYPASSRLS`. A membership in `cloudsqlsuperuser` that was left in place shows up as `CREATEDB`/`CREATEROLE` reachable through the membership, so the `REVOKE` is part of the step, not optional. The statements are recorded in the release record of that first rollout with who ran them and when; they are never repeated by a later release, and a new environment (staging, production) repeats the step once.

## Partition window and ANALYZE

Runbook entry RB-12 (05 PERF-27, SCH-13; 04 §1.6 rule 2; dev-guide DG-MIG). `audit_event`, `subledger_line` and the other partitioned tables hold one partition per UTC month from 2018-01 to 2032-12 plus a default partition. Rows that fall outside the window land in the default partition and lose their pruning, so the window is extended before it closes.

```sql
SELECT relname FROM pg_class
WHERE relname ~ '^audit_event_p[0-9]{6}$' ORDER BY relname DESC LIMIT 1;
```

Expected: a partition at least 24 months ahead of today. The periodic task `partition_window_check` (SCH-13, 05:00 UTC) will warn in the logs and notify operators when the window ends within 24 months; until it is built, run the query at each quarterly access review. To extend the window, add a forward-fix revision (`make revision MSG="extend partitions to 2040" ITEM=<item>`) that calls `migration_ops.create_monthly_partitions` for every partitioned table and release it like any migration (RB-02); partitions are never added by hand.

`ANALYZE` needs the table owner, so the api and worker never run it. After a bulk load or a data migration, run as `erev_owner` through the pipeline identity (RB-11):

```sql
ANALYZE erev.schedule_line, erev.subledger_line, erev.contract_event, erev.obligation_version;
```

Hosted deployments otherwise rely on autovacuum; locally `make perf-seed` runs the same statement after the month-23 lock (PERF-27).

### PostgreSQL lock table

The partitioned tables also decide how large PostgreSQL's shared lock table must be (05 §2.7 lock budget). The server sizes that table once, when it starts, as `max_locks_per_transaction × (max_connections + max_prepared_transactions)` slots for every database it serves. A statement that reads `audit_event`, `schedule_line` or `subledger_line` without a value for the partition column locks the parent, its indexes, every partition and every index of every partition, and keeps those locks until its transaction ends: 1,092, 910 and 1,092 relations, 3,094 together at revision 0072. Measured on the compose PostgreSQL, a contract computation holds 2,253 locks in one session and an audit-chain verification 1,134; a statement that names the month holds about ten.

Requirement, self-hosted and hosted alike:

```text
max_locks_per_transaction × (max_connections + max_prepared_transactions)
    ≥ ⌊0.8 × max_connections⌋ × partition lock footprint + relations of the database
```

At revision 0072 that is `max_locks_per_transaction ≥ 2526` at 100 connections (3,094 partition locks, 5,044 relations). PostgreSQL's default is 64.

| Deployment | Where the setting comes from |
|---|---|
| Compose | `deploy/compose.yaml` starts the `postgres` service with `-c max_locks_per_transaction=4096` |
| Hosted (Cloud SQL) | The Terraform variable `db_max_locks_per_transaction` sets the database flag (default 4096; the variable refuses less than 3072). Changing the flag restarts the instance |
| A PostgreSQL you run yourself | `max_locks_per_transaction = 4096` in `postgresql.conf`, or `ALTER SYSTEM SET max_locks_per_transaction = 4096;` as a superuser, then **restart the server**. The setting is read at server start only; `pg_reload_conf()` does not apply it |

PostgreSQL 17 computes 327 MB of shared memory at 4096 with 100 connections (143 MB at the default 64) and 1,136 MB with 600 connections (168 MB), so size the host for it.

```sql
SHOW max_locks_per_transaction;
SHOW max_connections;
SELECT count(*) FROM pg_locks;
```

Under `production`, `erev doctor` evaluates the rule on the live catalogue as the check `lock-budget`, so a window extension or a new index on a partitioned table that uses up the margin fails the rollout gate (RB-02) before it fails a transaction. On a server left at the default it prints:

```text
FAIL lock-budget: max_locks_per_transaction 64 × (max_connections 100 + max_prepared_transactions 0) gives 6400 lock slots; 80 sessions × 3094 partition locks + 5044 relations need 252564 (05 §2.7): set max_locks_per_transaction to at least 2526 and restart PostgreSQL
```

What SQLSTATE 53200 means. When the lock table is full, PostgreSQL answers `ERROR: out of shared memory` with the hint `You might need to increase "max_locks_per_transaction".` to the statement that needed the next slot. That can be any statement of any session in any database of the server, not the session that holds most locks. The statement's transaction rolls back as a whole: nothing is written in part, and the ledger and the audit chain are not damaged. The api answers that request with 503 and `Retry-After: 5` and logs `http.server_unavailable` (a warning) with `sqlstate` `53200`: nothing was saved, and the same request can be sent again. A contract computation that meets it records no result — no `FAILED` computation and no exception item, so the fault does not hold a period's gates. A job attempt fails and is retried while its kind's retry policy has attempts left, and ends `FAILED` otherwise ("Stuck and failed jobs"). The api answers in the same way when the server is shutting down or starting, or a connection is refused or lost (SQLSTATE class 53, `08000`, `08001`, `08003`, `08004`, `08006`, `57P01`, `57P02`, `57P03`); every other database error is still a 500 with `http.unhandled_error`. Measured on a server left at the default 64: nine sessions each held the 3,094-relation footprint and the tenth was refused. It is a capacity signal. Response:

1. Confirm it: the `sqlstate` in the api or worker log, `SHOW max_locks_per_transaction`, and `SELECT count(*) FROM pg_locks` while the load runs.
2. Raise `max_locks_per_transaction` to at least the value `erev doctor` names and restart PostgreSQL in a maintenance window (hosted: change `db_max_locks_per_transaction` and apply).
3. Until the restart, lower the concurrency that holds locks: `EREV_WORKER_CONCURRENCY` and the number of worker instances. Leave `max_connections` where the connection budget needs it (05 §2.7).

### Requests answered 409 lock-conflict, 409 period-closed or 503

These answers say "not now", not "wrong" (04 API-C-04, API-C-05, §15.2, DB-07; 05 §2.7, SCH-05; dev-guide DG-KRN-IDEM-03, DG-KRN-ERR-06). None of them is kept for the request's `Idempotency-Key`: the same request, sent again as it is, runs.

| Answer | What happened | What to do |
|---|---|---|
| 409 `lock-conflict` | Another transaction held a row the request needed for longer than the lock timeout (10 seconds; rule `LOCK_TIMEOUT`), the two deadlocked, or one could not be serialized against the other. Nothing was saved. | Send it again. |
| 409 `period-closed` to a posting | The period was locked while the posting waited for it (`EREV-LED-003`). Nothing was saved. | Send it again: the amount is planned into the next open period. |
| 503 with `Retry-After: 5` and no problem slug | The database could not serve the request at that moment — the api logs `http.server_unavailable` with the `sqlstate` (class 53, a lost or refused connection, a server shutting down or starting) — or the api's own connection pool gave no connection within its wait: the same log line with `driver_error_class` `sqlalchemy.exc.TimeoutError` and no `sqlstate`. | Send it again after the pause the header names. For the pool, read `erev_db_pool_in_use{component="api"}`: a pool held full by slow requests points at the database or at lock waits, not at the pool's size (05 §2.7). For SQLSTATE 53200 see "PostgreSQL lock table". |
| 503 `statement-timeout` with `Retry-After: 30` | PostgreSQL cancelled a statement of the request at the 60-second limit of a unit of work. The api logs `http.statement_timeout` with `sqlstate` `57014`; the PostgreSQL log names the statement (`canceling statement due to statement timeout`). Nothing was saved. | Send it again later. When the same request ends this way repeatedly, its statement is too slow or waits behind locks: look at `pg_stat_activity` and `pg_locks` while it runs. |

Locking a period. A lock decision that was answered 409 `lock-conflict` — a posting, or a recalculation of one of the entity's contracts after the period's close run, held the period's row beyond the lock timeout, the next period's row was held, or a state change of an earlier period of the entity and book was being decided at that moment (that one is answered at once, and the request to lock can meet it too; 04 DB-07) — is simply decided again. So is a decision that waited for a posting in flight and was then refused by the coverage guard (409 `invalid-transition`, rule `S15-R-18c`); that refusal is kept for its key, so the next decision is a new submission with a new `Idempotency-Key`, as the screen sends it. There is no gate on imports or posting jobs in progress: nothing has to be stopped before a period is locked. From the period's close run until its lock, the decision waits for every recalculation in flight of that entity's contracts and then reads what it left to post — which is how "Close run out of date" reaches a decision that was already submitted; a contract command of that entity sent while the lock is being decided waits for the decision in the same way and then goes on — its amounts of the period, if any, are placed as after any lock; when the decision takes longer than the lock timeout the command is answered 409 `lock-conflict` instead and is sent again.

The scheduler meets the same conflicts. `period_auto_open` (05 SCH-05) logs `period_auto_open.lock_conflict` with the entity, the book, the period and the `sqlstate` when a row it needs is held, and `period_auto_open.statement_timeout` when PostgreSQL cancelled a statement of the opening; it goes on with the other due periods in the same run and opens the one it left at its next run, fifteen minutes later. Later due periods of the same entity and book are logged `period_auto_open.refused` in that run, because a period opens only after the one before it; the next run opens them in order. A period that is logged `period_auto_open.statement_timeout` at every run has an opening that is too slow for the 60-second limit: look at the statement in the PostgreSQL log. The same run defers a failed re-marking job again (see "Re-marking after a lock opened the next period"); when that deferral meets one of the two, it logs `period_open_redirty.lock_conflict` or `period_open_redirty.statement_timeout` with the period state, serves the other period states and workspaces, and makes the deferral at its next run. Any other failure of one opening or one deferral is logged at error level — `period_auto_open.failed` or `period_open_redirty.failed`, with the period or period state and the error's class — and the run goes on with the others; a period that is logged so at every run needs engineering, and the other workspaces are not held up by it. Only when the database cannot serve at all (the errors answered 503 without a slug, above) does the run end, to be made again fifteen minutes later. The same holds for a whole workspace: when its due periods or its failed re-marking jobs cannot be read, the run logs `period_auto_open.read_failed` or `period_open_redirty.read_failed` at error level with the workspace, leaves that step out for it and goes on with the next workspace; `period_auto_open.completed` counts such workspaces in `tenants_skipped`. Each of these error lines carries `error_class` and `error_at`, the module and line of the code where the error was raised, and never the error's message.

## Locking the digest bucket retention policy

Runbook entry RB-13 (05 SAR-31; DPL-35). The daily digest of every tenant is copied to the bucket `erev-audit-digests-<env>` whose retention policy of 7 years Terraform creates unlocked. Locking it is a one-time manual step, because a locked policy can never be removed or shortened and the bucket can then not be deleted until every object has aged out.

```sh
gcloud storage buckets describe gs://erev-audit-digests-<env> --format='value(retention_policy)'
gcloud storage buckets update gs://erev-audit-digests-<env> --lock-retention-period
gcloud storage buckets describe gs://erev-audit-digests-<env> --format='value(retention_policy.isLocked)'
```

Expected: the first command shows `retentionPeriod: 220752000`; the second asks for confirmation; the third prints `True`. Run it once per environment, after the first digest copy has been verified against a tenant's `audit_chain_verification` row, and record who ran it and when in the evidence store. The executor is `<digest bucket lock owner>` (UI-3).

## Personal data erasure

Runbook entry RB-14 (05 PRV-02, PRV-03, PRV-04, PRV-06, PRV-07, PRV-09, PRV-11, OPR-10; 04 API-R-05, API-R-12, T-PLT-02, T-PLT-29, §15.4 `FILE_RETENTION_ACTIVE`, `FILE_SHREDDED`, `FILE_EVIDENCE_HELD`, `FILE_SHRED_APPROVAL_REQUIRED`; 03 REQ-SEC-007; BUILD_SPEC SOP-5). Erasure is two audited commands, never a database change; both are built by SOP-5 (`POST /api/v1/users/{membership_id}/anonymise`, permission `user.manage`, MFA; `POST /api/v1/files/{id}/shred`, permission `settings.manage`, MFA, reason required). An erasure request is recorded on the request's file and nothing is deleted by hand. eRev 1.0 has no self-service erasure endpoint. A data-subject request reaches the tenant, who is the controller (PRV-02); a hosted operator only assists (PRV-11) and never runs these commands in a tenant without the tenant's instruction. The tenant's own administrators run every step below; each names its expected result and its refusal.

| Step | Command | Expected result | Refusals |
|---|---|---|---|
| 1. Identify the member | `GET /api/v1/users?search=<email>` as a `user.manage` holder; note the `membership_id`. | One membership of the person in this workspace (or none: the person was never a member here). | none |
| 2. Erase the identity | `POST /api/v1/users/{membership_id}/anonymise` with body `{"reason": "<DSR reference, at least 10 characters>"}`, by an administrator other than the person, after a TOTP step-up at most five minutes old (`POST /api/v1/session/mfa`). | 200 with the membership `REMOVED`. The person's account now reads `Erased user <8 hex>` / `erased+<user id>@invalid.erev`, has no password or external id and status `DISABLED`; every session of the person is ended; the membership in this workspace is removed with its roles revoked, and the person's memberships in every other workspace are removed too, each audited there as `tenant_membership.remove`. Read `erasure` in the 200 body: `status` `COMPLETE` means nothing else is owed; `COMPLETION_PENDING` lists the other workspaces (`other_workspaces_completion_pending`) still owed their `app_user.anonymise` completion event, and `next_step` says what to do — run the command again with a new `Idempotency-Key` once the 200 is in (the identity change is durable by then); that run writes the completion event in each owed workspace and answers 200 with `status` `COMPLETE`; any later run answers 409 `PRV-07`. The acting workspace's own `app_user.anonymise` event lists the same workspaces under `other_tenants_completion_pending`. When the person had no other workspace the first 200 is already `COMPLETE` and a second run answers 409 `PRV-07` at once. An administrator of an owed workspace may run the continuation there, through the person's removed membership, with their own step-up and a new key. Completion is a manual second command: eRev delivers nothing in the background. | 403 `mfa-step-up-required` (step up again); 403 `forbidden` (your own membership: another administrator must run it); 404 `not-found` (unknown membership, or a platform operator's identity); 422 `validation-failed` (reason shorter than 10 characters); 409 `invalid-transition` rule `PRV-07` (already erased). A failure while removing a membership in another workspace returns the problem and erases nothing in this workspace: run the command again (a new `Idempotency-Key`); it resumes the removals still owed and never repeats an audit event. |
| 3. Find the person's documents | `GET /api/v1/attachments?subject_type=…&subject_id=…` over the records the request names; `GET /api/v1/files/{id}` shows `legal_hold`, `retention_until` and `shredded_at`. | The list of `file_object` ids whose bytes hold the person's data (contract documents, imports naming the person). | none |
| 4. Shred each document | `POST /api/v1/files/{id}/shred` with body `{"reason": "<DSR reference>"}`, by a `settings.manage` holder (that permission is MFA-gated, API-C-03) whose permission covers every legal entity of the records that reference the file — every entity when one of them names none, or when no record references the file. | 200 with `shredded_at` set: the shred is decided and on the audit chain, and `GET /api/v1/files/{id}/content` returns 404 `not-found` with rule `FILE_SHREDDED` from then on. The wrapped data key of the file is destroyed right after — a durable marker is left, so the ciphertext is unreadable; the row and its SHA-256 stay as evidence (D-43) — and `GET /api/v1/files/{id}` then shows `shred_completed_at`. If it stays empty the file store did not answer: send the command again with a new `Idempotency-Key`, which completes the shred and answers the completed file (under the same key the first answer is replayed and nothing is done) — while the store still does not answer, the repeat fails with 500 and changes nothing — or leave it to the platform's sweep, which tries every ten minutes. | 403 `forbidden` rule `T-PLT-10` (the file belongs to records of legal entities your `settings.manage` does not cover — the answer names none of them; an administrator of those entities, or of every entity, runs this step and the request below); 409 `invalid-transition` rule `FILE_RETENTION_ACTIVE` (legal hold, or `retention_until` after today: the hold prevails until the retention command lifts it); rule `FILE_SHREDDED` (already shredded); rule `FILE_EVIDENCE_HELD` (the file is the evidence of a standing record, which the message names: the source of an import that is submitted, approved or committed, a dataset of a period lock, a journal batch file, an impact preview, an audit digest — for an import that is not yet committed, have it rejected or its approval request withdrawn and shred then; otherwise record the refusal on the request's file, see below); rule `FILE_SHRED_APPROVAL_REQUIRED` (an uploaded document that a record rests on: the source of a committed import, the source file of a signed reconciliation, the legacy database of a migration whose capture is relied on, the SSP study of a submitted version, the attachment of a submitted manual adjustment of USD 10,000.00 or more. Send `POST /api/v1/files/{id}/request-shred` with body `{"reason": "<DSR reference, at least 10 characters>"}` after a TOTP step-up at most five minutes old (`POST /api/v1/session/mfa`); 200 returns the `approval_request_id` and changes nothing yet. A Controller whose role covers the record's entities — never the requester — approves it in the approvals queue, and the approval shreds the file as the system on the requester's behalf: `GET /api/v1/files/{id}` then shows `shredded_at`, and the `file_object.shred` audit event names the approval request. A rejection leaves the file as it is: record it on the request's file. When the approval answers that the records holding the file have changed, have the request rejected and send a new one); rule `PRV-06` (a purpose stored in plaintext — report outputs, evidence packs, journal exports, impact previews, AI logs, digests, posting responses, extracted document text — cannot be shredded in 1.0; see the open items). |
| 5. Record completion | Keep the DSR reference and the audit actions as the evidence: `app_user.anonymise`, `tenant_membership.remove`, and for each file `file_object.shred` — the decision: who, when, why — and `file_object.shred_complete` — when the key was destroyed, by which road, and until when a deleted copy of it stays recoverable (`irreversible_after`) (`GET /api/v1/audit-events?action=…`). | The audit events carry the old e-mail only as an HMAC (`{"hmac", "length"}`, PRV-04) and never the old display name; the person's earlier events keep their pseudonymous `actor_id` (PRV-03, REQ-SEC-007). | none |
| 6. Verify the shreds | `erev verify --all-tenants` (RB-06 / RB-08 verifier). | Each shredded file reports `shredded` once its sidecar is gone. | `shredded_sidecar_present`: the row says shredded and a key is in the store. With `shred_completed_at` empty the completion is owed: retry step 4 for that file with a new `Idempotency-Key`, and the command completes it. With `shred_completed_at` set, a key was put back into the store after the shred was completed (an object restored by hand): the file stays refused by its row, step 4 answers `FILE_SHREDDED`, and 1.0 has no command that destroys the key a second time — report it to the platform operator. |

Run the erasure in the production workspace. A sandbox copy shares its stored files with the workspace it was copied from: for such a file `POST /api/v1/files/{id}/shred`, `POST /api/v1/files/{id}/request-shred` and the approval of a shred request answer 403 `sandbox-restricted` in the sandbox, each with a `DENIED` audit event (05 SBX-08), and the shred of step 4 in production also makes the copy's content unreadable — the copy answers `FILE_SHREDDED` once the key is destroyed (`shred_completed_at`), not before — so nothing is left to shred there. A document that was uploaded into a sandbox itself is the sandbox's own, and a reset replaces the sandbox and deletes nothing: run steps 3 and 4 in that sandbox as well, where the same commands shred it — before the sandbox is reset. A sandbox that a reset has replaced is archived and cannot be opened, so no command reaches what it stored; a shred that was decided there before the reset is still completed, by the platform's sweep, which goes through archived workspaces too.

Loss of access is immediate; irreversibility is not. From the decision of the shred (`shredded_at`) the application answers `FILE_SHREDDED` at once; the key is destroyed right after (`shred_completed_at`), but the deleted sidecar remains recoverable from the bucket's soft delete for 7 days (hosted), and locally from every backup tarball that still holds it. Database backups hold no data keys, so they never resurrect a file. The erasure record therefore names the shred — its decision and the destruction of the key, `shredded_at` and `shred_completed_at`, normally the same moment — and the date the erasure is final: 7 days after the key was destroyed hosted, and locally the day the last backup set containing the sidecar is deleted under the backup retention of RB-04. Never delete a `.dek` file by hand; the shred command is the only erasure path. Completion and residuals (OPR-10): a shredded file's sidecar generations stay recoverable from the object store's soft delete for 7 days, and database backups never hold data keys, so erasure of documents is final 7 days after the key was destroyed once backup retention lapses; the `file_object.shred_complete` audit event's `detail.irreversible_after` names the last hard-delete time (the event of the decision, `file_object.shred`, carries nothing of the store). Accounting records, audit events and security events are retained for `platform.audit_retention_years` under the tenant's legal obligations (PRV-09); security-log IP addresses and user agents stay with the log for that period.

A shred that is decided and not completed (05 PRV-07 b, OPR-24, SCH-16). `file.shred` and the approval of a shred request record the decision first — the row and the audit event `file_object.shred` — and destroy the key after that commit, so a command that fails has destroyed nothing. When the file store does not answer at that moment the command still answers 200: the workspace refuses the file from then on (a sandbox copied from it before the shred does not yet: its copy of the row is not stamped, and it reads the document until the key is destroyed — 05 SBX-03), `GET /api/v1/files/{id}` shows `shredded_at` with an empty `shred_completed_at`, and the verifier of step 6 reports `shredded_sidecar_present` for it. The worker task `erev.file_shred_completion` runs every 10 minutes and completes every such file whose decision is at least 2 minutes old, at most 200 per workspace and run; the administrator's repeat of step 4, with a new `Idempotency-Key`, completes it at once. Either writes the audit event `file_object.shred_complete`. A workspace that still holds such a file 60 minutes after its decision raises the operator alert `FILE_SHRED_INCOMPLETE`: the log line `operator_alert.raised` (warning level) with the tenant id, the number of files and the age of the oldest decision in minutes — it names no file — once an hour while it lasts; a hosted deployment warns on that line. What is at stake while the alert lasts: the workspace itself refuses each such file, but every sandbox copied from it before the decision still reads the document until the completion (05 SBX-03). For the operator: the worker's log line `file_shred.completion_failed` names the file id, the road and the error type of each failed attempt. Repair what it names — the store's reachability, the worker's credentials for the bucket, or, for `GenerationConflict`, whatever restores objects in the bucket beside the shred. Nothing is done in the workspace and no `.dek` is deleted by hand: once the store answers, the next run completes every owed file and the alert stops. A sandbox never completes the shred of a file it shares with the workspace it was copied from; that workspace does.

Not erased in 1.0 (record these on the request's file; each is a supervisor proposal pending the privacy owner, D-97 §C): the person's MFA factor and recovery codes (proposed: deleted with the identity), `access_review_item.user_email_snapshot` (proposed: rewritten to the HMAC form), `file_object.original_filename` (proposed: replaced by the id-based name), `contract_cost_asset.payee` (proposed: retained as an accounting record, Art. 17(3)(b)/(e), the denial logged), `password_reset_token.ip_address` (swept 30 days after the token expires), and the bytes of plaintext-purpose files (erasure unruled; refused by rule `PRV-06`). Files that are the evidence of a standing record are not erased either (rule `FILE_EVIDENCE_HELD`; supervisor rulings R-30 and R-49): lock datasets, journal batch files, report outputs of locked runs, approval impact previews and audit digests are accounting records retained under PRV-09 (GDPR Art. 17(3)(b), (e)), and an uploaded document that a record rests on (rule `FILE_SHRED_APPROVAL_REQUIRED`) is not shredded by one administrator: it is erased through the approved request of step 4, while the record itself — an import's rows with their tokenised values, its lineage, totals and approval; a reconciliation's totals and sign-offs — stays. Every refusal of `file.shred` is the recorded outcome of the request: the audit log carries it as a `DENIED` `file_object.shred` event that names the record (`GET /api/v1/audit-events?action=file_object.shred`); note it on the request's file, as for `contract_cost_asset.payee`. A legal hold prevails over erasure while it lasts. Never delete `.dek` sidecars or objects by hand: `file.shred` is the only supported path.

## Adapter credentials

Runbook entry RB-15 (05 ADP-14, KEY-09; REQ-INT-006). Adapter credentials for Salesforce, Stripe, NetSuite and QuickBooks Online are never in `.env`, code or logs.

- Storing: `integration_connection.secret_ref` names a Secret Manager secret of the workspace's own namespace at a pinned version, `tenant-<tenant id>-<name>@<version number>` — the tenant id in its lower-case form, the secret's id in the project being the deployment's secret prefix followed by `tenant-<tenant id>-<name>`. A reference outside that namespace — another workspace's secret, or a platform secret such as the SMTP password — is refused when the connection is saved (422 on `secret_ref`) and is served nothing when it is read: the test action records a failure and the webhook receiver answers 401 (05 KEY-09, ADP-14 rev 1.47). Adapters receive the value as a `SecretStr` at call time and persist nothing. Connections to the in-process mock routers of local environments carry `secret_ref = null` and send no credential, because the mock routes are unauthenticated.
- General ledger connections (BUILD_SPEC CLO-15): a connection of adapter `NETSUITE` or `QUICKBOOKS_ONLINE` that takes journals names its `base_url`, the entities it covers and its non-secret `config` — `max_lines_per_chunk`, and for QuickBooks Online the company's `realm_id`. In this release the two adapters are delivered against the in-process mock routers (03 REQ-JE-014, REQ-JE-015): they send no credential, so such a connection carries `secret_ref = null`, and a connection pointed at a real NetSuite or QuickBooks Online company is refused by that system — the batch is `failed` with its answer. Production workspaces export by `CSV`.
- Rotating: add a new secret version, run the connection's test action from the integration screen (which records the UTC time of the test), then disable the previous version; the tenant drives its own rotation.
- Testing: the test action sends one authenticated request and records `last_tested_at` and the outcome; a failure is a SEV-3 for that tenant until the credential is corrected.
- Logs: structlog drops any key matching password, secret, token, api_key, authorization or cookie and redacts such values in messages (SAR-19), so a credential that appears in a log is itself an incident (RB-10).
- Hosted deployments: the first release ships no live adapter, and `deploy/terraform/gcp/main.tf` grants no identity read access to the workspace namespace — the api and the worker read the named platform secrets and the tenant audit keys only. A connection whose secret is in Secret Manager therefore fails closed there: its test records a failure and its webhook receiver answers 401. That is a known limitation of the hosted shape (item OPS-IAM-ADAPTER-SECRETS-1; supervisor ruling R-108 (b) (4)); the binding belongs to the release that ships a live adapter. Do not grant it by hand. Not verifiable without a deployment.
- Sandboxes: nobody provisions secrets under `tenant-<sandbox tenant id>-`, and nothing in a sandbox can use one — an outbound adapter other than the CSV download cannot be active there, an inbound connection cannot be created and a webhook endpoint cannot be active (05 SBX-08; 04 DB-15).

## Upgrade validation before a new engine release

Runbook entry RB-16 (05 §7.8 REL-06, REL-01 to REL-05; §3.11 RCP-29; §7.1 OPR-07; OPR-16, OPR-23; dev-guide DG-ENG-10). The validation depends on the version level of `ENGINE_VERSION`.

| Level | Gates before release | Replay | Differences |
|---|---|---|---|
| PATCH | `make ci`, `make answer-keys`, `make parity`, `make properties`, `make test-pg`, `make controls-report` recorded in `release-manifest.json` (`make release-manifest STRICT=1`) | none | Any difference fails the release |
| MINOR | The gates above | RCP-29 sample on first start: every group with activity in an open period plus a stratified 5% sample per tenant (at least 20 groups) | Any output difference fails the release |
| MAJOR | The gates above | RCP-29 sample | Written to an `UPGRADE_VALIDATE` report; tenant approval before true-ups post in the first open period |

Procedure: (1) build and validate the images with `make docker-build` and promote the same image digests through staging first (OPR-07); (2) take the pre-migration backup (RB-02); (3) run the migration job, then start the new revision; (4) `erev doctor` and `erev verify --all-tenants`; (5) MINOR and MAJOR: wait for the RCP-29 replay jobs and read their result before enabling the release for tenants.

Rolling back:

- No schema change in the release: either route traffic back to the previous Cloud Run revision (`gcloud run services update-traffic erev-api --to-revisions=<previous revision>=100`, and the same for the worker services) or redeploy the previous image digest; both are the build that staging validated before.
- Schema changed: the previous image is not ready against the new schema by design, because `readyz` requires `alembic_version` to equal the running code's head and otherwise answers 503 `{"status": "not_ready", "failed": ["migrations"]}` (OPR-23). Do not route traffic to it. Production is forward-fix: ship a corrected build that migrates forward, or recover by RB-04 "Hosted restore" at the pre-migration backup and cut over. Never `alembic downgrade` (DG-MIG-08).
- Every rollback is recorded with the manifests of both builds and, when a clone was cut over to, the `platform.restore_applied` events.

## Reclaiming performance sandbox storage

Archived `perf-run-*` sandboxes of `make perf` accumulate in the dev database (DG-PERF-07). Reclaim the storage by rebuilding the dev database and the perf tenant:

```sh
make db-reset
make perf-seed
```

`make db-reset` refuses while the dev stack runs (`FAIL db-reset: dev stack running; run make dev-down first`); `make perf-seed` (phase PRF; not built yet) rebuilds `perf-volume` and its snapshot from the generator manifest.

## Files and attachments

Operational behaviour of the file store, uploads and attachments (03 REQ-PLT-035, REQ-SEC-012; 04 T-PLT-29, T-PLT-30, DB-11; 05 UPL-01 to UPL-04, UPL-10, PRV-06; dev-guide DG-KRN-FILE-01 to DG-KRN-FILE-03, DG-KRN-IDEM-04).

| Behaviour | Rule | Evidence |
|---|---|---|
| Upload limits | `POST /api/v1/files` accepts `ATTACHMENT` and `SSP_STUDY` (pdf, docx, xlsx, csv, png, jpg, eml; 25 MiB), `IMPORT_SOURCE` (xlsx, csv; 50 MiB) and `LEGACY_DATABASE` (SQLite; 500 MiB). The type is decided by content, and a file name must carry a matching extension. Macro-enabled or binary workbooks, OLE2 containers and archives are refused, and an OOXML file must stay within the ZIP limits (10,000 entries, 250 MiB uncompressed, 150 MiB per entry, 100:1 per entry, no nested archives or `..` paths). A refusal returns 422 `upload-type-not-allowed` naming the purpose's limit and stores nothing. | none; refused uploads write no row |
| Body limit | The api refuses a `POST /api/v1/files` body above 500 MiB plus 64 KiB of multipart framing before reading it, and every other body above 1 MiB. | none |
| Content addressing | Objects live at `${EREV_FILE_ROOT}/<tenant id>/<purpose>/<sha256 of the plaintext>`. Uploading identical content of the same purpose again returns the existing file. | `file_object.sha256`, `storage_key`; audit action `file.upload` for created files |
| Encryption | Import sources, attachments, SSP studies, legacy databases and snapshot datasets are stored as AES-256-GCM ciphertext under a random per-file data key. The key, wrapped under `kek:1`, is the sidecar `<storage key>.dek` next to the object, never in the database. | sidecar files under `EREV_FILE_ROOT` |
| Immutability | `erev_app` holds `SELECT`, `INSERT` and `UPDATE` of `legal_hold`, `retention_until` and the shredding columns only. DELETE and TRUNCATE raise `EREV-IMM-001`; changing any other column raises `EREV-TRN-001`. | grants; `tg_file_object__immutable`, `tg_file_object__truncate`, `tg_file_object__transition` |
| Downloads | `GET /api/v1/files/{id}/content` returns the plaintext with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox`. | none |
| Attachment void | Only the uploader voids an attachment, once, with a reason. A void is refused with `EREV-ATT-001` (409 `invalid-transition`) while an approved approval request relies on the subject. | audit actions `file_attachment.create`, `file_attachment.void`; `tg_file_attachment__void` |
| Large command responses | A first command response above 1 MiB is stored as a `REPORT_OUTPUT` file and replayed from it. | `idempotency_record.response_file_id` |

- Back up `EREV_FILE_ROOT` together with the database and the `.env` (DG-MK-backup). A file whose sidecar is missing, or a restore under another `EREV_ENCRYPTION_KEY`, cannot be read.
- Never copy, move or delete `.dek` sidecars by hand. Deleting a sidecar shreds its file for good; the audited `file.shred` command is the only supported erasure path (05 PRV-07).
- Uploads above 1 MiB are spooled to the temporary directory while they are checked. Under make that is `.run/tmp`; an api host needs free temporary space of at least the largest upload limit per concurrent upload.

## Approvals

Operational behaviour of approval requests (03 REQ-PLT-011, REQ-PLT-013 to REQ-PLT-017; 04 T-PLT-17 to T-PLT-21, T-REF-24 to T-REF-27, DB-04, DB-10, §14.3, §16.10; dev-guide DG-KRN-APR-01 to DG-KRN-APR-08).

| Behaviour | Rule | Evidence |
|---|---|---|
| Routing | A new request takes its steps from the most specific matching rule of the PUBLISHED `APPROVAL_ROUTING` rule set versions in force. Without a match it gets the item type's own steps. A matching rule adds steps or raises a requirement and never lowers them: a request always keeps the item type's own permission, approver count, second step and role (the Controller's approval of a period lock, and the Controller's second step of an estimate version with a P&L impact of USD 50,000.00 or more, among them), whatever the rule names. A requirement one of the rule's steps already meets is not added again. A routing rule without a condition is refused when it is saved and never matches. | `approval_request.routing_rule_set_version_id`, `routing_rule_id`; audit `approval_request.submit` names the rule |
| Auto-approval | Rules approve system-originated standard items only. A tenant's own rule can name two item types: a contract activation an integration originated — an API client, or `SYSTEM` acting for no user, and every event of the contract written by an integration, so a draft a person changed, directly or through an approved override, estimate version, attribute change or combination, waits for a person — and an import commit uploaded by an API client. The legacy SSP replay of a migration and the setup grants are approved only by the rule sets provisioning seeds (`AUTO-MIG-01`, `AUTO-BOOTSTRAP`); a rule of another rule set that names them approves nothing, and the two seeded rule sets take no further version (409 `configuration-frozen`). When a PUBLISHED `AUTO_APPROVAL` rule with `{"auto_approve": true}` matches such an item, the request is approved at submission. Every other item — and the same item prepared by a person — waits for a person whatever a published rule says; a rule that names no item type, or an item type a person always approves, is refused when it is saved and at publication, and evaluating a rule set version against a case answers as a submission would. The first step is `APPROVED`, any later steps `SKIPPED`, and one `AUTO_APPROVE` decision by `SYSTEM` names the rule set version and rule. | `approval_decision.auto_rule_set_version_id`, `auto_rule_id`; audit `approval_request.auto_approve` |
| Setup grants | Every new tenant has rule set `AUTO-BOOTSTRAP`. It approves the role assignments the bootstrap Tenant Admin requests (the administrator named at provisioning, whose own `tenant_admin` grant it also approved) while `tenant.setup_completed_at` is NULL and nobody else has ever been an active access approver. Once setup completes the rule never applies again; and from the moment a second person has been active while holding `access.approve`, every assignment waits for a person — for good, also when that approver is later suspended, removed or loses the role. Suspending, removing or revoking is never refused for that reason, so a workspace can fall back to one access approver, whose own requests then have no decider: that state is repaired by the platform operator, not by the rule. Another Tenant Admin's requests always wait. No other rule can approve a role assignment. Review these grants in the next access review. | decisions naming rule `AUTO-BOOTSTRAP` |
| Published rule sets | A published rule set version never changes. Its rules and test cases are refused with `EREV-CFG-002` unless the version is `DRAFT` or `TESTED`. Only provisioning inserts the rules of the system versions it seeds as published. | `tg_rule__config_child`, `tg_rule_test_case__config_child` |
| Separation | A preparer never approves their own item, directly or on behalf of someone, and an approver or delegator decides at most one step of a request. Refusals are 403 `self-approval` and 409 `approver-already-decided`; the database refuses the same rows with `EREV-APR-001` and `EREV-APR-002`. | `approval_decision`; `tg_approval_decision__sod` |
| Stale subject | When the subject's content hash differs from the submitted hash, or from the hash the approver reviewed, the decision voids the request with `void_reason` `STALE_SUBJECT` and returns 409 `stale-approval`. The void is committed although the decision is refused. A command that changes a subject with a pending request voids it in the same transaction. | `approval_request.status` `VOIDED`, `voided_at`; audit action `approval_request.void` |
| Withdrawal | Only the preparer withdraws a pending request. Open steps become `VOIDED` and `void_reason` is `WITHDRAWN_BY_PREPARER`. | `approval_request.status` `WITHDRAWN`; audit action `approval_request.withdraw` |
| Bulk approval | Up to 200 items per call. Each item is decided in its own transaction, with its own decision, preview hash and separation checks, so one refused item leaves the others approved. | one `approval_decision` per approved item |
| Delegation | A delegation lasts at most 90 days. A delegate decides only while the delegation is in force and not revoked, the delegator's membership is active and the delegator still holds the step permission for every entity of the request. One delegation must cover all of them; the delegate's own scope and a delegation are never added up. A delegation hands over the permission, not the view: the delegate decides, is listed and is notified for a request only when the delegate's own roles cover every entity of it, and is otherwise refused before anything of the request is read. A person the item excludes (its preparer, the runner of a journal run, the author of a judgement record, the author of a combination proposal, the owner of a waived item) is refused through a delegate as in person; among several delegations the one of a delegator who may decide is used. The decision records the delegation and the delegator. | `approval_decision.delegation_id`, `on_behalf_of_id`; `ck_approval_delegation__validity` |
| Inbox visibility | `GET /api/v1/approvals` shows a request to its preparer, to everyone who decided it and to holders of any of its step permissions for at least one of its entities, directly or through a delegation in force, always within the member's own entity scope; a request outside it answers 404 like an unknown id, on the read and on approve, reject and withdraw alike. A request names the legal entities of its item (`entity_id` for one, `entity_ids` for several, `is_all_entities` when it spans every entity; the API shows them as `entities`, `entity_count` and `all_entities`, and the audit event of the submission records them); deciding it needs the step permission, and the step's role when it names one, for every one of them. The entities are read again at the decision: an item that names other entities than at submission is voided as stale (`STALE_SUBJECT`) and must be submitted again. A role assignment is bound to the entities of the grant it proposes, so granting a role for all entities takes `access.approve` for all entities. "Waiting for me" (`assigned_to_me=true`) keeps pending requests whose active step the member can decide — with the step's role, when it names one — and did not prepare or decide. A member who is the only person able to decide a later step of a request is kept for that step: the earlier step answers 409 `invalid-transition` and the request is not waiting for that member until the later step is active. A preparer submits only an item whose every legal entity its own roles cover; a contract item names the contracting entities of every contract combined with it. Approving, alone or in bulk, needs a TOTP verification at most five minutes old; otherwise the API answers 403 `mfa-step-up-required`. | `approval_request`, `approval_step`, `approval_delegation` |
| Delegation lifecycle | A member delegates only approval permissions they hold, to another active member, with a reason of at least 10 characters. Only the delegator revokes a delegation, and a revoked delegation cannot be revoked again. | audit actions `approval_delegation.create`, `approval_delegation.revoke`; `approval_delegation.revoked_at` |

## Users and memberships

Operational behaviour of invitations, role requests and membership commands (03 REQ-PLT-008, REQ-PLT-010, REQ-PLT-012; 04 API-R-05, T-PLT-07, T-PLT-10, SMAP-14; PRD SM-13, BR-PLT-02, BR-PLT-06; BUILD_SPEC PLF-17). Every route needs `user.manage`.

| Behaviour | Rule | Evidence |
|---|---|---|
| Invitation | `POST /api/v1/users` creates an invited membership, reuses the person's account when the email is known, and emails a link that expires after 7 days. The outbox row of the invitation names the link's token by reference and never holds it (as the reset email does); the link is composed when the email is sent, so a link cannot be read out of `erev.outbox_message`. Until a reused account accepts, the user list and detail show the email as the name, and null last sign-in and MFA status; `PATCH /api/v1/users/<id>` renames only a person the invitation itself added, otherwise 409 `invalid-transition` (D-80). The email of a platform operator is refused with 422 on `email` (rule `T-PLT-02`); operators reach a workspace only through a support grant. Each role becomes one `ROLE_ASSIGNMENT` approval request for an `access.approve` holder other than the inviter. While setup is incomplete, rule `AUTO-BOOTSTRAP` approves the requests a Tenant Admin prepares. | audit `tenant_membership.invite`; `approval_request` subject `ROLE_ASSIGNMENT`; `outbox_message` topic `EMAIL` |
| Requested roles | A requested role has no `role_assignment` row until it is approved. The request's impact preview file holds the proposed row as `after` and the member's current roles as `before`. Separation of duties is checked when the request is made and again at approval; a conflict returns 409 `sod-conflict` and writes nothing. Roles scoped to entity codes are refused with `EREV-REF-002` until legal entities exist. | `approval_request.impact_preview_file_id`; audit `role_assignment.create` |
| Suspend and remove | Both need a reason of at least 10 characters and end the member's sessions in the workspace. Removal also revokes the member's roles and cancels an open invitation; the membership and its history stay. An administrator cannot suspend, reactivate, remove or reset their own membership. | audit `tenant_membership.suspend`, `tenant_membership.remove`, `role_assignment.revoke`; `user_session.end_reason` `REVOKED` |
| Reset MFA | Needs a TOTP verification at most five minutes old and an `ACTIVE` or `SUSPENDED` membership; an invitation not yet accepted returns 409 `invalid-transition`, and a platform operator's membership returns 404. The member's factor is disabled and every session of the person ends, so they enrol again at the next sign-in. The reset is audited in this workspace and in every other workspace where the person is ACTIVE (`detail.acting_tenant_id`). | `security_event` `MFA_RESET`; audit `user_mfa_factor.reset` |
| Resend invitation | Replaces the link and restarts the 7-day lifetime; the earlier link stops working. | audit `tenant_membership.resend_invitation`; a second `EMAIL` message |

## Roles and role assignments

Operational behaviour of custom roles, role changes and role assignments (03 REQ-PLT-008 to REQ-PLT-010; 04 API-R-06, T-PLT-09 to T-PLT-12, SMAP-14; PRD SM-04, SM-13, ERR-22; BUILD_SPEC PLF-18). Every route needs `role.manage`.

| Behaviour | Rule | Evidence |
|---|---|---|
| Custom roles | `POST /api/v1/roles` creates an inactive role without permissions and a `ROLE_CHANGE` approval request for an `access.approve` holder other than the author. Approval grants the proposed permissions and activates the role. A rejected or voided request leaves the role inactive, so it cannot be assigned. | audit `role.create`, `role.change`; `approval_request` subject `ROLE_CHANGE` |
| Role changes | `POST /api/v1/roles/{id}/propose-change` needs `If-Match` and a different permission list, and a role waits for one change at a time. System roles never change (409 `invalid-transition`). A list that would give a member holding the role a conflicting combination without an approved exception is refused with 409 `sod-conflict`, when proposed and again at approval. Approving a change voids the pending assignment requests for that role. | audit `role.change` with `permissions_added` and `permissions_removed`; `approval_request.void_reason` `STALE_SUBJECT` |
| Assignments | `POST /api/v1/role-assignments` requests one role for one member for all entities; entity codes are refused with `EREV-REF-002` until legal entities exist. It is refused when the member already holds or waits for the role, and with 409 `sod-conflict` when the combination meets an SoD rule without an approved exception. | `approval_request` subject `ROLE_ASSIGNMENT`; audit `role_assignment.create` |
| Revocation | `POST /api/v1/role-assignments/{id}/revoke` takes effect at once and needs a reason of at least 10 characters. An administrator cannot revoke their own roles. | `role_assignment.revoked_at`, `revoked_by`, `revoked_by_kind`; audit `role_assignment.revoke` |

## Separation of duties

Operational behaviour of SoD rule versions and SoD exceptions (03 REQ-PLT-010; 04 API-R-07, T-PLT-13, T-PLT-14; PRD SM-04, SM-13, ERR-22; BUILD_SPEC PLF-19, BS1-D-29). Every route needs `role.manage`; approvals need `access.approve` by another administrator. A rule is the workspace's: proposing a version of one needs `role.manage` for all entities. An exception is a member's: asking for one and revoking one need `role.manage` for every entity of the member's roles, and an administrator whose scope does not cover them is answered 403 by name.

| Behaviour | Rule | Evidence |
|---|---|---|
| Rule versions | `POST /api/v1/sod-rules/{code}/versions` records the next version DRAFT, tests and submits it in one command, and opens a `ROLE_CHANGE` approval request. Approval publishes the version and supersedes the published one from that moment; rejection leaves it `REJECTED`, withdrawal or a stale request `WITHDRAWN`. Only one version of a rule is open at a time. Publishing voids pending exception requests of the rule. | `sod_rule` versions; audit `sod_rule.create`, `sod_rule.publish`, `sod_rule.supersede` |
| Exception requests | `POST /api/v1/sod-exceptions` needs a published rule, a member, a compensating control of at least 10 characters, a comment and a validity of at most 366 days. It opens a `SOD_EXCEPTION` request; no auto-approval rule can approve it. | `sod_exception` status `REQUESTED`; audit `sod_exception.request`, `sod_exception.approve`, `sod_exception.reject`, `sod_exception.void` |
| Using an exception | While an exception is `APPROVED`, unrevoked and in force, the SoD check accepts the combination for that member and rule. `POST /api/v1/role-assignments` may name it in `sod_exception_id`; the approved assignment stores the covering exception. | `role_assignment.sod_exception_id` |
| Revocation | `POST /api/v1/sod-exceptions/{id}/revoke` ends an approved exception at once and needs a reason of at least 10 characters. Assignments it covered stay and become conflicts without an exception: revoke the role first. | `sod_exception.revoked_at`, `revoked_by`, `revoked_by_kind`; audit `sod_exception.revoke` |

## Access reviews

Operational behaviour of access review campaigns (03 REQ-CTL-006; 04 API-R-51, T-PLT-40, T-PLT-41, DB-10, §14.3 item 3; PRD BR-PLT-02; BUILD_SPEC PLF-28). Every route needs `access.approve` for all entities: a campaign covers every member of the workspace.

| Behaviour | Rule | Evidence |
|---|---|---|
| Create | `POST /api/v1/access-reviews` `{name, as_of, reviewer_membership_ids}` records a DRAFT campaign. Reviewers are active members holding `access.approve` for all entities through a role of their own, each named once; `as_of` cannot be in the future. | audit `access_review_campaign.create` |
| Start | `POST /api/v1/access-reviews/{id}/start` snapshots every membership that is not removed: the email, the last sign-in and each role in force with its entity codes, grant date and grantor. Setup grants show the grantor `AUTO-BOOTSTRAP`, a human approval the approver's name. It writes one PENDING item per member and a JSON snapshot file of purpose `REPORT_OUTPUT`. | `access_review_campaign.snapshot_file_id`; audit `access_review_item.create` per item and `access_review_campaign.start` |
| Decide | A reviewer of the campaign certifies an item, or requests revocation with a comment of at least 10 characters. Decisions are final. A reviewer never decides their own membership: the API answers 403 `self-approval` and the database refuses the row with `EREV-APR-001`. | `access_review_item.decision`, `reviewer_id`, `decided_at`; audit `access_review_item.decide`; `tg_access_review_item__separation` |
| Revocation | Revoke the member's role (`POST /api/v1/role-assignments/{id}/revoke`) or remove the member, then call `POST /api/v1/access-reviews/{id}/items/{item_id}/confirm-revocation`. Before the revocation it answers 409 `invalid-transition`. Confirmation stays possible after the campaign completes. | `access_review_item.revocation_completed_at`; decision `REVOKED`; audit `access_review_item.confirm_revocation` |
| Complete and cancel | `POST /api/v1/access-reviews/{id}/complete` needs every item decided; otherwise it answers 409 "Decide <n> pending items before completing the campaign." `POST /api/v1/access-reviews/{id}/cancel` ends a draft campaign or a campaign in review; its items stay. | audit `access_review_campaign.complete`, `access_review_campaign.cancel` |

- Download the snapshot with `GET /api/v1/files/{snapshot_file_id}/content` (the member who started the campaign, or a holder of `audit.read`) and keep it with the certification as evidence.

## Engine releases

Operational behaviour of release stamping (05 REL-03; 04 T-PLT-38; dev-guide DG-ENG-10; BUILD_SPEC PLF-20).

| Behaviour | Rule | Evidence |
|---|---|---|
| Startup | The api records the running release when it starts serving, and the worker before it consumes jobs. A release is the pair engine version and build; the first process of a new pair inserts the row and later processes reuse it. | `engine_release` row; `deployed_at` is the first start |
| With a manifest | When `release-manifest.json` exists at the repository root (`make release-manifest`), the build, the control impact tags and the results of the `ci`, `parity`, `answer-keys`, `properties`, `test-pg` and `controls-report` gates come from it. A manifest that names another engine version or schema revision, has no build, or is not valid JSON stops the process at startup. | `engine_release.build_sha`, `control_impact_tags`, `gate_results` |
| Without a manifest | `dev`, `test` and `e2e` derive the release from `erev_engine.ENGINE_VERSION`, `git rev-parse HEAD` (`dev` without git) and the code's Alembic head. `production` refuses to start without a manifest. | `engine_release.schema_revision` |
| Writing the manifest | `make release-manifest` (offline; never runs a gate) writes `release-manifest.json` from the engine version, `git rev-parse HEAD`, the code's Alembic head, the gate reports under `.run/reports/<gate>/report.json` (`PASS`, `FAIL`, or `NOT_RUN` when a report is absent, from another build or from a dirty worktree) and the `control_impact_tags` whose `impact_paths` globs match the paths changed since the latest `v*` tag (the whole tree while no tag exists). `STRICT=1` fails unless every gate is `PASS` on a clean worktree. | `release-manifest.json`; `.run/reports/release-manifest/report.json` |
| Building images | `make docker-build` (supervisor target) writes the embedded manifest (no image identities inside it) under the run directory, exports the captured commit once with `git archive <build sha>`, places the manifest in that context and builds the api, worker and web images from it; the api and worker Dockerfiles copy the manifest to `/app/release-manifest.json`. The target neither reads nor writes `release-manifest.json` at the repository root, so the checkout is as it was afterwards. The build refuses a manifest naming another build than the captured one or carrying image identities, fails when the context or the source changes while building, and fails when a built image holds `pip` or a file with a setuid or setgid bit (`stage` `hardening` in the report). `NO_CACHE=1` rebuilds every layer. `docker compose build` builds from the working tree and copies `release-manifest.json` from the repository root, so write that file first with `make release-manifest EMBEDDED=1` ("Start" above). | `.run/reports/docker-build/report.json`: the attestation (`build_sha`, `tree_sha`, `context_sha256`, `manifest_sha256`, `images.<name>.tag`, `digest`, `manifest_sha256`, `hardened`, `clean_source`) and `release-manifest.embedded.json`, the exact bytes the images carry |
| Rolling deploy | Every deferred job records the enqueuing process's release (`params.engine_release_id`). A worker of another release re-defers the job for 30 seconds up to 10 times, then fails it with `release-mismatch` (503) and notifies the initiator; a job queued before REL-05 (no pin) follows the same cycle, so workers of the previous release may still take it during the roll-out, and then fails closed with the detail "no enqueuing release": re-submit it under the current release. A malformed pin fails at once with `validation-failed`. Nothing runs under a mixed release (05 REL-05). Finish a roll-out within five minutes, or expect `release-mismatch` failures to re-submit. | `job.problem` type `release-mismatch` or `validation-failed`; log events `job.release_mismatch_deferred`, `job.release_mismatch`, `job.release_pin_malformed` |

- `engine_release` is append-only: `erev_app` may read and insert rows, never update or delete them.
- A manifest written for an earlier build stops a newer build at startup. Run `make release-manifest` again, or delete `release-manifest.json` in `dev` to fall back to derivation.
- A production container without the manifest does not serve: the api logs the startup stack trace, whose last line is the reason (`…ReleaseManifestError: release-manifest.json is required in production (REL-03)`), then `Application startup failed. Exiting.`, and exits 3; the worker exits 1 with the same error. A malformed or mismatching manifest is refused the same way, the last line naming what differs (`the release manifest is not valid JSON`, `names another engine version`, `names another schema revision`, `carries no build_sha`). A stack trace longer than 2,000 characters is logged from its end, so the reason is always there. Both fire before any database connection, so a database error in the same log has another cause. Rebuild the image with `make docker-build`; never mount a manifest of another build into a container.
- `GET /releases` and `GET /me` `engine_release` show which manifest a running deployment stamped: `build_sha` is the manifest's, `gate_results` hold the six stored gates, and `control_impact_tags` the controls the build touched.
- The api and worker each log `release.stamped` at startup with `engine_release_id`, `engine_version`, `build_sha`, `schema_revision` and `source`; the ids of a healthy deployment are equal and name the single `engine_release` row. A manifest whose gates are `NOT_RUN` boots (non-strict) but is not release acceptance: `make release-manifest STRICT=1` must exit 0 for the build that ships, and `.run/reports/docker-build/report.json` must show `clean_source` true and the api and worker `manifest_sha256` equal to the embedded copy.

## Profile, workspace settings and saved views

Operational behaviour of the profile, display preferences, workspace settings and saved views (04 API-R-03, API-R-04, API-R-16, API-S-Me, T-PLT-01, T-PLT-02, T-PLT-37; BUILD_SPEC PLF-21).

| Behaviour | Rule | Evidence |
|---|---|---|
| Profile | `GET /api/v1/me` returns the signed-in member, the memberships of the workspaces the person can see (the one opened last first), the grants in the active workspace, MFA status, display preferences, the effective negative-number style, default locale and AI switch, the engine release the api stamped at startup and the unread notification count. | `app_user`; `tenant_membership.last_opened_at`; `engine_release` |
| Display preferences | `PATCH /api/v1/me/preferences` changes any of `format_locale`, `theme`, `density`, `shortcuts_enabled` and `tour_completed`. A null member returns to its default; an unknown member is refused with 422. Preferences follow the person into every workspace and write no audit event. | `app_user.preferences` |
| Workspace settings | `GET /api/v1/tenant` and `PATCH /api/v1/tenant` need `settings.manage` for all entities in an MFA-verified session. The update takes `display_name` and `default_locale` and needs `If-Match` with the latest ETag: 428 without it, 412 when the workspace changed since. A request naming `kind` is refused with 409 `tenant-kind-immutable`. | audit `tenant.update`; `tenant.row_version` |
| Saved views | `POST /api/v1/saved-views` saves a grid view or a favourite for the member; a name is unique per member and screen. The list shows the member's own views and the views others share. Only the owner changes or deletes a view; anyone else gets 404. A favourite needs `config {target, path, label}`. Saved views write no audit event. | `saved_view` rows; `is_shared`, `is_favourite` |

- The negative-number style and the AI switch are registry settings. Change them through a policy version under approval, never through `PATCH /tenant`.

## Sign-in throttling and sessions

Operational behaviour of password sign-in and browser sessions (03 REQ-PLT-004, REQ-SEC-004; 05 SAR-06, SAR-09 to SAR-11, SAR-13; dev-guide DG-API-07).

| Behaviour | Rule | Evidence |
|---|---|---|
| Lockout | Five consecutive wrong passwords lock the account for 15 minutes. The fifth attempt and every attempt during the lock return 423 `account-locked`. The lock lapses by itself, and a correct password afterwards resets the failure count. An email that has no account is counted and answered the same way, so that the answers do not tell whether an account exists: its count is read from the security log, and its lock is an `ACCOUNT_LOCKED` event with `email_sha256`, no user and `detail.locked_until`. There is nothing to unlock for such an email. | `security_event` kinds `LOGIN_FAILED` (`detail.failed_login_count`) and `ACCOUNT_LOCKED` |
| Sign-in rate limit | At most 10 attempts per minute per client address and email, counted together for `POST /api/v1/session/login` and `POST /api/v1/session/mfa`, and 50 per minute per client address, counted together for those two and every other unauthenticated route of the sign-in surface: `POST /api/v1/oauth/token`, `POST /api/v1/session/invitations/lookup`, `POST /api/v1/session/accept-invitation`, `POST /api/v1/session/password-reset/confirm` and the OIDC start and callback routes. A refused attempt returns 429 `rate-limited` with `Retry-After` and is not counted. Many people behind one address share its 50 per minute. | none; refused attempts write no event |
| Idle timeout | The workspace's `platform.session_idle_minutes` without a request (5 to 240, default 30). Before a workspace is chosen, the shortest value among the user's active workspaces applies. The next request returns 401 `session-expired`. | `security_event` `SESSION_EXPIRED`; `user_session.end_reason` `IDLE_TIMEOUT` |
| Absolute timeout | 12 hours after sign-in, including across workspace switches. | `SESSION_EXPIRED`; `end_reason` `ABSOLUTE_TIMEOUT` |
| Sign-out | `POST /api/v1/session/logout` ends the session server-side, and the old cookie is refused. | `LOGOUT`; `end_reason` `LOGOUT` |

- The limiter counts inside each api process. A deployment with several api instances therefore allows up to the limit per instance; the hosted Cloud Armor throttle adds a per-address ceiling at the load balancer (05 DPL-41).
- Client addresses come from `X-Forwarded-For`, counted `EREV_TRUSTED_PROXY_HOPS` from the right (0 locally, 1 behind compose nginx, 2 hosted). A wrong value makes every request appear to come from the proxy, so one noisy client throttles everyone behind it.
- Restarting the api clears the rate-limit counters but not the lockouts or sessions, which live in the database.

## Invitations and password reset

Operational behaviour of invitation acceptance, password reset and password change (04 T-PLT-07, T-PLT-42, §16.12; 05 SAR-10; BUILD_SPEC PLF-15). Every token is 256 random bits sent only in an email link fragment; the database keeps its SHA-256.

| Behaviour | Rule | Evidence |
|---|---|---|
| Invitation | `POST /api/v1/session/invitations/lookup` shows the workspace, inviter and email of an open invitation. `POST /api/v1/session/accept-invitation` sets the first password under the password policy, or verifies an existing user's password with the sign-in lockout. It makes the membership ACTIVE, seeds the notification preferences and opens a session in the workspace. The link expires 7 days after it is sent; an expired, used or unknown link returns 404. | `security_event` `TENANT_SELECTED`; audit action `membership.accept` |
| Reset request | `POST /api/v1/session/password-reset` always returns 202. An ACTIVE user with a password gets a 60-minute link, the earlier open links stop working, and the email waits in the outbox of the workspace the user opened last. The outbox row names the link's token by reference (`payload.link_token`) and never holds it: the token is derived from the platform security key when the request is recorded and again when the email is sent, and no table holds it. A user with no active workspace gets no email. | `PASSWORD_RESET_REQUESTED`; `password_reset_token` |
| Reset limits | At most 5 links per user and 20 requests per client address per rolling hour. An excess request still returns 202 and sends nothing. | `PASSWORD_RESET_REQUESTED` with outcome `DENIED` and `detail.limit` `user` or `address` |
| Reset confirm | `POST /api/v1/session/password-reset/confirm` spends the link once, sets the password, clears a lockout and ends every session of the user. | `PASSWORD_RESET_COMPLETED`, `PASSWORD_CHANGED`; `end_reason` `PASSWORD_CHANGED` |
| Password change | `POST /api/v1/me/password` needs the current password. It ends the user's other sessions and keeps the user signed in under a rotated token: the 204 sets a new `erev_session` cookie, and the presented token stops working (05 SAR-09; D-80). | `PASSWORD_CHANGED` naming the new session; `end_reason` `PASSWORD_CHANGED` for the other sessions and `REVOKED` for the presented one |

- The invitation lookup visits the workspaces one by one under the directory scope, so each lookup writes one `PLATFORM_SCOPE_USED` event.
- The address limit counts inside each api process, like the sign-in limiter. The per-user limit counts stored links and holds across processes.
- A user whose reset link expired requests a new one; links expire 60 minutes after the request.

## Multi-factor authentication

Operational behaviour of TOTP enrolment, the sign-in challenge, recovery codes and step-up (03 REQ-PLT-005; 04 T-PLT-04, T-PLT-05; 05 SAR-07, SAR-09, SAR-26; BUILD_SPEC BS1-D-19, BS1-D-30).

| Behaviour | Rule | Evidence |
|---|---|---|
| Enrolment | `POST /api/v1/me/mfa/enroll` stores a new 160-bit seed as an `erev1` envelope under `kek:1`, bound to the factor row; enrolling again before confirmation replaces the pending seed. `POST /api/v1/me/mfa/confirm` with a first valid code confirms the factor, returns ten recovery codes once and rotates the session as verified. | `security_event` `MFA_ENROLMENT_STARTED` at each `enroll` (`detail.reseeded`), `MFA_ENROLLED` at `confirm`; audit action `mfa_factor.enrol` in the tenant of each ACTIVE membership |
| Codes | SHA-1, six digits, a 30-second step and one step either side. A code for a step at or before `last_used_step` is refused, so each code works once. | `user_mfa_factor.last_used_step` |
| Second factor | The rule is the user's (03 REQ-PLT-005; 05 SAR-26). A session owes enrolment while MFA is mandatory for its user — a `requires_mfa` permission through any ACTIVE membership, or an operator — and no factor is confirmed; it owes the challenge while the user has a confirmed factor and the session is not verified. Such a session gets 403 `mfa-required` on every route except `GET /api/v1/session`, `POST /api/v1/session/logout` and the routes that settle the step (`POST /api/v1/me/mfa/enroll` and `/confirm`; `POST /api/v1/session/mfa`). Sign-in and `GET /api/v1/session` report `mfa_enrolment_required` or `mfa_required`. A route guarded by a `requires_mfa` permission keeps its own check. | audit `DENIED` with `detail.reason` `mfa-required` and `detail.step` (`enrolment` or `challenge`) |
| Challenge | `POST /api/v1/session/mfa` with `code` or `recovery_code` rotates the session with `mfa_verified_at` set. A wrong, replayed or spent code returns 422 `validation-failed` on the field sent. | `MFA_CHALLENGE_FAILED`; `RECOVERY_CODE_USED` |
| Challenge limits | The challenge shares the sign-in rate limit, and a refused attempt returns 429 `rate-limited` with `Retry-After`. The fifth wrong code or recovery code since the last successful verification and the latest lock locks the account for 15 minutes and returns 423 `account-locked`; during the lock the route and password sign-in return 423 without checking anything. Signing in again does not restart the count. | `MFA_CHALLENGE_FAILED`, `ACCOUNT_LOCKED` with `detail.method`; `app_user.locked_until` |
| Recovery codes | Ten per batch, stored as argon2id hashes. A code is spent once: `used_at` changes only from NULL (`tg_user_recovery_code__transition`). Only the newest batch is valid. `POST /api/v1/me/recovery-codes` issues a new batch and needs step-up. | `user_recovery_code.used_at`, `batch_id`; `security_event` `RECOVERY_CODES_REGENERATED` with the batch id |
| Step-up | Step-up routes need an MFA verification at most five minutes old; otherwise 403 `mfa-step-up-required`. | `user_session.mfa_verified_at` |

- Seeds decrypt only with `EREV_ENCRYPTION_KEY`. A restore without the `.env` saved with the backup (DG-MK-backup) leaves every enrolled user unable to verify.
- Codes depend on the api host clock. A drift of more than 30 seconds refuses valid codes, so keep time synchronisation running on every api host.

## Rate limits and metrics

Request limits (05 SAR-13; 04 API-C-16; REQ-PLT-037) are sliding one-minute windows kept in memory by each
api process (`erev_api.auth.ratelimit`). A refused request answers 429 `rate-limited` with a `Retry-After`
header and the detail "Too many requests. Try again in N seconds."; the refusal is raised before any handler
runs, so it is never stored as an idempotent response and the same `Idempotency-Key` runs the command once
the window has passed.

| Bucket | Key | Limit |
|---|---|---|
| Sign-in and MFA challenge | client address and normalised email; client address | 10 per minute; 50 per minute (see "Sign-in throttling and sessions") |
| The other unauthenticated routes of the sign-in surface (token endpoint, invitation lookup and acceptance, password-reset confirmation, OIDC start and callback) | client address, the same bucket as sign-in | 50 per minute |
| `POST /api/v1/oauth/token` | OAuth client id, after the address | 30 per minute |
| Authenticated browser traffic | session id | 1,200 per minute |
| API clients (bearer tokens) | `api_client.id` | `api_client.rate_limit_per_minute`, default 600 |

The default is published in the OpenAPI document's `info.description` ("Rate limit: 600 requests per minute
per API client (default); enforced per api process."). DG-API-07: the windows are per api process, so a
deployment with N api instances behind nginx admits up to about N times the limit for one key; nginx does not
aggregate them. A client's limit is set when the client is requested (`rate_limit_per_minute`);
no command changes it afterwards — another limit is another client and another request.

Metrics (04 API-R-53; 05 MET-01 to MET-11; REQ-OPS-012) are served by the api process at `GET /metrics`,
outside `/api/v1` and outside the OpenAPI document, in the Prometheus text format 0.0.4. The endpoint is off by
default: set `EREV_METRICS_ENABLED=true` and `EREV_METRICS_TOKEN=<token>` (a missing token refuses to start),
and scrape with `Authorization: Bearer <token>`; without it the route answers 404 while disabled and 401 without
the bearer. nginx does not proxy `/metrics`; point the scraper at the api process directly.

```
curl -H "Authorization: Bearer $EREV_METRICS_TOKEN" http://127.0.0.1:8190/metrics
```

Label values never carry tenant ids, user ids or amounts (`erev_api.controls.metrics.validate_labels` refuses
them before a sample is stored); HTTP series use the route template, never the concrete path. The api process
measures `erev_http_requests_total`, `erev_http_request_duration_seconds` and `erev_db_pool_in_use{component="api"}`
itself; the worker-side series (`erev_jobs_total`, `erev_job_duration_seconds`, `erev_job_queue_depth`,
`erev_computation_duration_seconds`, `erev_close_step_duration_seconds`, `erev_outbox_messages`,
`erev_export_failures_total`, `erev_audit_chain_verification_failures_total`) are exposed with their `# HELP` /
`# TYPE` lines and carry samples once the scrape-time database read of BUILD_SPEC BS1-D-36 lands.
