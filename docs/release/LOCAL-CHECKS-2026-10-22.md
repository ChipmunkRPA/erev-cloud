# Local checks — October 22, 2026

Scope: repository completion only; no deployment or live business data. Source commit
`1d8e81e5d6334d7115f57c5ab2046691b3b2418a`, tree
`f99ec06d58c05d7fcadcbfb85e31ba42672ef2fb`.

- Compose build/start/readiness/worker/smoke/cleanup passed; both checked ports available.
- Unauthenticated local ZAP baseline passed its gate: no high/medium alerts, one low and
  three informational alerts. Inner ZAP exit 2 denotes warnings, not zero alerts.
  This is not a complete authenticated security review.
- License inventory: 142 packages, eight allowlisted, zero findings or allowlist errors.
- Secret scan: 4,167 files, nine allowlisted, zero findings or unused allowlist entries.
- Public repository has only main and no open pull requests at this checkpoint.
  No tracked research-harness or docs/research files.

## Restore drill finding and correction

The disposable eight-tenant restore drill failed at doctor, after successful backup,
volume destruction, fresh-server restore and integrity verification. All 1,818 files,
11 backup-time anchors and 1,529 encrypted envelopes verified. Schema revision 0334.
Cleanup completed. Row comparison did not execute; this is not a passing restore drill.

Doctor allowed only application session settings, so it rejected the PostgreSQL
`track_commit_timestamp` parameter read by five commit-time evidence functions.
The correction explicitly permits that single server parameter, keeps unknown app/server
settings and dynamic arguments rejected, and updates the diagnostic wording and runbook.
It does not change monetary calculations, timestamps, recovery verification, permissions
or database server configuration. This reference check does not verify the setting is on.

Necessary verification of the correction: 39 baseline unit cases and four real PostgreSQL
17 doctor cases passed, including freshly migrated schema, unknown-setting refusal,
disabled-trigger detection and failed-audit detection. Scoped lint and types pass.
The complete restore drill must be rerun on the corrected source before recording success.

Machine reports remain in ignored .run/reports; raw backup logs and key material are not
published. These results are bounded local evidence and do not complete outstanding
Reporting functionality or pending accounting choices.
