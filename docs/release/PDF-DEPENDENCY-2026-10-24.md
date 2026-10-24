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

## Linux/container follow-up

Verified commit 907557117c184ccce051e714f4983a383e04fa2c, source tree
beb33bb261b2cdeb6348d9950fdccff3876c10bc. The three-image local build and image hardening
probes pass. API and worker embed manifest
970743622b7cabd8aff65a5670f48d0ec178267856c7cca1459bf5c699915a49.

- API: sha256:16f487c5f13014af2075bb67312b461820a0883e8a2495c37979e64a57c1b441
- Worker: sha256:af0a60d54521a73a1b0204f2f7ca839fb282d91ccff492584f3d9c04974044f5
- Web: sha256:aeb36dc5d65b5850e5a7fa4d1cc36a0513ccf8e407097f2529255aabbdf15ec3

The new worker ran under its unprivileged default user, without network, on a read-only root
filesystem and a bounded temporary filesystem. The probe confirmed installed patched versions,
isolated extraction of the four-page synthetic PDF fixture, refusal of a 1 GiB allocation by
the Linux address-space limit, and CPU-limit termination. The temporary container was removed.
These are targeted runtime probes covering the earlier macOS skips, not a full Linux test suite.

Local Terraform fmt/init/validate also passes for ten files and four pinned providers on the
same commit. Initialization used backend=false; there was no plan/apply or remote-state action.
Machine-readable evidence is in .run/reports/docker-build/ and .run/reports/tf-validate/.
The compose/restore/baseline scan checkpoints remain dated historical evidence. No deployment.
