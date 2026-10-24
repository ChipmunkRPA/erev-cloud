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
