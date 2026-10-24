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
