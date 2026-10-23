# Runtime dependency security refresh — October 22, 2026

The audit of main `62a65d5` found six Python advisory records across three packages;
npm runtime dependencies had no advisory records. This supersedes the October 15
clean-dependency checkpoint as evidence of what the current advisory databases report.

| Package | Previous lock | Fixed lock | Advisory records |
| --- | --- | --- | --- |
| certifi | 2026.7.22 | 2026.10.19 | PYSEC-2026-4320 |
| opentelemetry-api | 1.44.0 | 1.45.1 | CVE-2026-114603 |
| pypdf | 6.20.1 | 6.21.1 | CVE-2026-113786, CVE-2026-113791, CVE-2026-113790, CVE-2026-113789 |

The Python project now requires the fixed PDF parser floor. Resolver constraints prevent
fresh resolutions from reintroducing the affected transitive certificate and trace-header
parser versions. The lock updates only these three packages and their distribution hashes.
The security floors do not add new runtime packages.

Necessary verification after synchronizing the frozen lock:

- Development dependency audit: zero vulnerabilities across all 86 pinned Python runtime
  distributions, including cross-platform requirements, and zero npm runtime advisories.
  Patched `uv.lock` SHA-256:
  `92ac8eac202c38862525d8bb07c455c1f98eb1434a5f37a24bd58105683c99c0`.
- PDF extraction, isolated-process behavior, HTTP middleware and health checks: 38 passed;
  two Linux-only resource-limit cases skipped on macOS. Three initial health setup errors
  were due to an unavailable default test database; all three subsequently passed against
  the task's disposable PostgreSQL server. No other database was modified.
- Frontend type checking and production build passed on `62a65d5`; this patch changes no
  frontend inputs. Reporting backend type checking passed across 212 source files before
  the dependency refresh. These are integration checks, not full accounting acceptance.

The development audit is not immutable release evidence. A clean committed audit must be
run before publishing this patch; its source binding and full machine-readable outputs live
under `.run/reports/audit-deps/`. Advisory results are dated snapshots and must be refreshed
for the final candidate. Container rebuild and Linux-specific checks remain separate release
checks. No deployment, hosted recovery exercise or independent accounting sign-off was performed.
