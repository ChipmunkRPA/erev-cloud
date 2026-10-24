# PDF parser dependency refresh — 2026-10-24

The current-main dependency audit found three new pypdf 6.21.1 advisory records:
CVE-2026-115572, CVE-2026-115585 and CVE-2026-115580. They concern excessive parsing work
from malformed/repeated indirect references and cross-reference tables. The upstream fixed
version is 6.21.2. The runtime dependency floor and frozen lock now use that version; no other
third-party package changed. Existing subprocess isolation and limits are preserved.

The patched audit covers all 86 pinned Python runtime distributions, including platform-marked
requirements, with zero vulnerabilities. npm runtime audit also reports zero advisories.
PDF extraction and isolation checks: 25 passed; two Linux-only resource-limit cases skipped
on macOS. This does not refresh the Linux/container execution evidence. Frontend production
build passed on pre-patch main (unchanged frontend inputs), with the existing large-chunk warning.

The committed-source audit is retained locally under .run/reports/audit-deps/ with source binding.
No deployment or production service was touched. Functional impairment, foreign split-layer
allocation and combined royalty scope decisions remain open; this is not system completion.
