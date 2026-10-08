# Repository verification — October 7, 2026 (America/Los_Angeles)

These are local repository checks, not deployment or accounting sign-off.

## Runtime dependency audit

`make audit-deps` passed against clean commit `87f53d1336016f02d543f4c37f37a88af6404afe` in an immutable
execution context. Completed at `2026-10-08T06:28:59.499431Z` (UTC).

- Python: all 77 pinned runtime distributions audited, zero vulnerabilities.
- npm runtime audit: zero advisories at every severity.
- Source/dependency bindings matched at completion; both scanners returned accepted results.
- Combined scanner output SHA-256: `29f7238ca4cffab044dd38b70b158f31dd0e3a092e39557ae58d47a6c235c2c6`.
- Python lock SHA-256: `f31a37107048eb4b4dfe174f1718b74fd848b5d99041a4cf418ca19c2232d7fd`.
- npm lock SHA-256: `fd512d40b74307934c45e70c0a070596b685d42bcc324c9694b245dcc6a3659a`.
- Local raw evidence: `.run/reports/audit-deps/` (report, both scanner outputs and audited requirements).

This evidence covers the pinned runtime dependency set at that revision. Repeat the gate
for the final release candidate; this is not a full application security assessment.

## Terraform validation repair

The initial `make tf-validate` on the same revision passed provider initialization and
formatting but failed to load all four provider schemas. The isolated checkout made the
absolute temporary directory too long for provider Unix sockets. A diagnostic validation
in the retained context succeeded when the temporary directory was relative to the module.

The validation script now uses `../../../.run/tmp/tf-provider` from the fixed module
working directory. Temporary sockets remain inside the execution context. A regression
runs a real Unix socket bind with a long inherited temporary path. No state, plan, apply,
cloud credentials or deployed resources are used. Formal `make tf-validate` passed against clean commit `40ae405fd58805386c239aafa73f63848f9f743f`
in an immutable execution context, finishing `2026-10-08T06:36:51.104233Z` (UTC).
Terraform 1.16.4 passed init (backend disabled), recursive formatting and
schema validation against all four locked providers. Input hashes matched before/after:
`42074943a8df4ee86cd77b4fb47a64c9802a0b125df26b55aa8a6396142ec5df`. Source and dependency bindings also matched.
Local raw evidence: `.run/reports/tf-validate/report.json`; console log:
`erev-tf-validate-verified.log`. Repeat this gate for the final release candidate.

## Remaining gates

Docker's CLI is installed, but its daemon was not running when checked. Container build,
Compose, ZAP and the isolated backup/restore drill remain unverified. Broader application
checks and independent revenue-accounting review are also still required.
