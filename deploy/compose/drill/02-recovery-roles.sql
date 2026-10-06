-- Recovery roles and the restore target of the restore drill's PostgreSQL container
-- (docs/dev-guide.md DG-MK-restore-drill; runbook RB-11 "The backup role and the restore-target
-- admin"; docs/05-ARCHITECTURE.md OPR-12; D-95).
--
-- Only the throwaway container of `make restore-drill` (compose project erev-verify-drill) mounts
-- this file, through deploy/compose/drill/override.yaml, beside initdb/01-roles.sql; the postgres
-- image runs both once, inside the container, when its volume is empty. The compose stack itself
-- never mounts it: a deployment's backup role and restore target are provisioned by its database
-- administrator (RB-11). Nothing on the host runs this file.
--
-- The statements are RB-11's, with the drill's database name. Passwords come from the container
-- environment, where the drill puts the two it generates for each run; never from this file.

\set ON_ERROR_STOP on

\getenv erev_backup_password EREV_DRILL_BACKUP_PASSWORD
\getenv erev_restore_admin_password EREV_DRILL_RESTORE_ADMIN_PASSWORD
\if :{?erev_backup_password}
\else
\set erev_backup_password ''
\endif
\if :{?erev_restore_admin_password}
\else
\set erev_restore_admin_password ''
\endif

-- Fail closed before any role exists when a password is missing or short.
SELECT length(:'erev_backup_password') >= 12 AND length(:'erev_restore_admin_password') >= 12
    AS erev_passwords_present \gset
\if :erev_passwords_present
\else
DO $$
BEGIN
    RAISE EXCEPTION 'EREV_DRILL_BACKUP_PASSWORD and EREV_DRILL_RESTORE_ADMIN_PASSWORD must each hold at least 12 characters';
END
$$;
\endif

-- erev_backup: reads every tenant's rows for pg_dump and writes nothing (RB-04, RB-11).
CREATE ROLE erev_backup WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
    PASSWORD :'erev_backup_password';
GRANT pg_read_all_data TO erev_backup;
GRANT CONNECT ON DATABASE erev TO erev_backup;

-- erev_restore_admin: loads a dump into the isolated clone; what it restores belongs to erev_owner.
CREATE ROLE erev_restore_admin WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS
    PASSWORD :'erev_restore_admin_password';
GRANT erev_owner TO erev_restore_admin;

-- The isolated clone of the drill, empty and owned by erev_owner.
CREATE DATABASE erev_rv_drill WITH OWNER erev_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE erev_rv_drill FROM PUBLIC;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev_rv_drill TO erev_owner;
GRANT CONNECT, TEMPORARY ON DATABASE erev_rv_drill TO erev_app;
GRANT CONNECT, CREATE, TEMPORARY ON DATABASE erev_rv_drill TO erev_restore_admin;
