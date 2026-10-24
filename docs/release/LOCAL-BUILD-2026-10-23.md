# Local build checkpoint — October 23, 2026

Source before this change: main `3a56f404cf00b1c2f70419b593a6eaa7ef2a445b`.

Frontend `npm run build` passes. Vite reports a large main bundle; this is build evidence,
not browser workflow or performance certification.

The local Docker daemon was started for isolated verification. The immutable-source
`make compose-verify` run remained at resolving the Dockerfile frontend image. Its build
clients were stopped before any application containers started. This is not a passing
container validation; registry resolution did not finish during the observed run.

The verification script now bounds the build as well as startup. The build budget defaults
to 1800 seconds and can be set through `EREV_COMPOSE_VERIFY_BUILD_TIMEOUT_SECONDS`.
Timeout stops the CLI process group, reports build failure with exit code 124, prevents
startup and restores/removes the temporary release manifest. The report retains the budget.

Four focused script checks pass: stalled build, stalled startup, embedded manifest and the
successful bring-up/smoke/teardown path. A real Docker run with a 20-second build budget
also reaches the budget while resolving the Dockerfile frontend and correctly records
`build-failed`, exit 124, startup/readiness not run, and the temporary manifest removed.
No erev-verify application containers remain. The short-budget run verifies timeout behavior,
not the default-budget build result. Shell syntax and diff checks pass.

Container build/readiness, baseline security scan and disposable restore drill remain open.
No deployment was performed. Shared-estimate application, combined actual progress and other
financial implementation gaps remain open; this operational fix does not replace that work.


## Current-main container verification completed

A new immutable-source run passes on main
`13ad937ca7a677fe26f08c2754016a268fb8b1c4`, tree
`d27894d8dae17cd8e700ca3d81d6ea9e27dd3653`.
`EREV_COMPOSE_VERIFY_BUILD_TIMEOUT_SECONDS=300 make compose-verify` exits zero:
API, worker and Web images build; the isolated migration exits successfully; startup,
API readiness, Web smoke/CSP, worker health and teardown all pass. No source or dependency
drift is reported. The prior Dockerfile frontend resolution stall did not recur.

Run `172b7441cd6f422a8739e88c9e510eb0`, finished 2026-10-24 00:52:05 UTC
(October 23 locally), retains embedded manifest digest
`af3096c733bb4b0e57fdb36fa8e0bea842033024a4d4f808beb87a7938b7fc9e`.
The authoritative local report is `.run/reports/compose-verify/report.json`.
Cleanup exits zero; the temporary root manifest is removed and no erev-verify containers
remain. This was isolated local verification, not deployment.

This supersedes the incomplete container build/readiness result above for that source commit.
It does not refresh the security baseline or restore drill, certify browser business workflows,
or complete shared-estimate application, special opening attribution or combined reassessment.
The independent accounting sign-off mentioned in historical objectives is outside the owner's
repository development completion scope.
