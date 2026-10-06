-- Roles and database of the compose PostgreSQL container (docs/05-ARCHITECTURE.md §8.2 DPL-10;
-- DG-RUN-08; D-42; G§5).
--
-- The postgres image runs this file once, inside the container, when volume erev-pg is empty
-- (/docker-entrypoint-initdb.d), as its bootstrap superuser. Nothing on the host runs it, and the
-- Homebrew server is never touched: role creation happens only inside this container.
--
-- Passwords come from the container environment (the environment file through compose.yaml), never
-- from this file. The attributes match the supervisor-provisioned roles of the Homebrew server.

\set ON_ERROR_STOP on

\getenv erev_owner_password EREV_COMPOSE_OWNER_PASSWORD
\getenv erev_app_password EREV_COMPOSE_APP_PASSWORD
\getenv postgres_password POSTGRES_PASSWORD
\if :{?erev_owner_password}
\else
\set erev_owner_password ''
\endif
\if :{?erev_app_password}
\else
\set erev_app_password ''
\endif
\if :{?postgres_password}
\else
\set postgres_password ''
\endif

-- Fail closed before any role exists when a password is missing or short.
SELECT length(:'erev_owner_password') >= 12 AND length(:'erev_app_password') >= 12
    AS erev_passwords_present \gset
\if :erev_passwords_present
\else
DO $$
BEGIN
    RAISE EXCEPTION 'EREV_COMPOSE_OWNER_PASSWORD and EREV_COMPOSE_APP_PASSWORD must each hold at least 12 characters';
END
$$;
\endif

-- Fail closed, also before any role exists, on the placeholders deploy/compose.env.example
-- ships (change-me-...): a copy of the example that nobody edited must start nothing (05 DPL-10
-- rev 1.53, ruling R-53 (6)). The third password is the image's own POSTGRES_PASSWORD, which the
-- environment file calls EREV_COMPOSE_POSTGRES_PASSWORD: the bootstrap superuser already has it.
-- The image has initialised the cluster by now, so after the correction the volume is removed.
SELECT :'erev_owner_password' LIKE 'change-me%' OR :'erev_app_password' LIKE 'change-me%'
    OR :'postgres_password' LIKE 'change-me%' AS erev_passwords_placeholder \gset
\if :erev_passwords_placeholder
DO $$
BEGIN
    RAISE EXCEPTION 'EREV_COMPOSE_POSTGRES_PASSWORD, EREV_COMPOSE_OWNER_PASSWORD and EREV_COMPOSE_APP_PASSWORD must not be the change-me placeholders of deploy/compose.env.example: generate each one, remove the database volume and start again';
END
$$;
\endif

-- erev_owner: migrations; owns the schema objects (D-42). No SUPERUSER, CREATEDB or CREATEROLE.
CREATE ROLE erev_owner WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'erev_owner_password';

-- erev_app: api and worker. Row-level security always applies to it (D-42; 05 TB-3).
CREATE ROLE erev_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    PASSWORD :'erev_app_password';

CREATE DATABASE erev WITH OWNER erev_owner ENCODING 'UTF8' TEMPLATE template0;

REVOKE ALL ON DATABASE erev FROM PUBLIC;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev TO erev_owner;
GRANT CONNECT, TEMPORARY ON DATABASE erev TO erev_app;
