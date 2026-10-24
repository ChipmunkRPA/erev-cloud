# Local service integration and baseline — 2026-10-24

Source commit ad2dea166b54121a35df320ff321f8dda1fa1884, tree
941ef1203e58 (full source binding retained in the machine report).
The ZAP wrapper built and started only the disposable erev-verify Compose project.
The embedded-manifest startup, migrations, API readiness, web response/CSP and worker heartbeat
checks passed. It then scanned the unauthenticated local web surface and removed that project's
containers and volumes. Post-run Docker inspection confirms no project containers/volumes remain.

The baseline gate passed with zero FAIL, high or medium alerts, one low alert (missing/invalid
Cross-Origin-Embedder-Policy) and three informational alert classes (modern application and
cacheability observations). ZAP exit 2 records warnings; it does not mean zero findings.
This is not an authenticated authorization or complete security review.

The first attempt failed before bringing up services because the isolated Docker configuration
could not discover Compose. Adding the installed CLI-plugin directory to that temporary config
resolved it. No existing credentials or other Docker projects were modified.

Machine-readable evidence and scanner output are retained under .run/reports/zap-baseline/,
including the nested compose-verify report. The restore drill still has its October 22 checkpoint;
it is not refreshed by this check. No deployment, live migration or external accounting sign-off.
Outstanding calculation-policy decisions and unfinished functionality are unchanged.

## Current-source disposable restore drill

The complete drill passed on 21f7c041aecb4cac95a892342a966c68a749a67b. All 12 stages passed,
including backup, destruction of the source volume, fresh-server restore, integrity verification,
doctor, row-count comparison and teardown. Eight tenants and 1,818 files verified without failures.
Across 722 tables, the source held 97,158 rows and the clone 97,160; no table was missing or had
fewer rows. The only increase was two erev.security_event rows from verification itself.

Backup took 23 seconds; destruction-to-verified-clone took 29 seconds; total drill 617 seconds.
Docker inspection after completion found no erev-verify-drill containers or volumes. The gate
removed its temporary execution context and backup/credential material; none was published.
Detailed evidence remains in .run/reports/restore-drill/, including backup.report.json,
restore-verify.report.json and row-counts.json. This supersedes the October 22 restore evidence
for the current schema; it remains a local synthetic-data exercise, not production recovery.
Outstanding functional gaps and pending owner calculation decisions remain unchanged.
