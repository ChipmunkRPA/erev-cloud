# Local package and configuration verification — October 22, 2026

Verified local source commit: `bbd64be808b00ba430540185de36afc0e432f4b4`.
Verified source tree: `a8174ecc5f7fa2292e150cfe9fc754ff5e29d25f`.
This checkpoint follows the runtime dependency security refresh. The only additional
configuration change normalizes whitespace in the Cloud SQL flags map; no infrastructure
values, state or cloud resources changed.

## Container packages

`make docker-build` completed from its exported source tree. All three images passed the
build's hardening probes; API and worker embedded the same verified release manifest.

| Image | Image digest |
| --- | --- |
| API | `sha256:3bc626ca7a7af16f9b91e19292391bf8c58eeea13c757cc5ca61f192da75f5b7` |
| Worker | `sha256:7f491ba2786f6020ac64d81fa3cc2f7eb03707136a935317558f97c33cf95384` |
| Web | `sha256:6254448d4e7a3d80f8022373e8df44f6def81fff42f344a0c83f6741a7643b58` |

Embedded manifest SHA-256:
`02088f10f24950467350a3f0dfb161fe69013d1b7661bb38283a964d6b3af4b6`.
Machine-readable build evidence remains in `.run/reports/docker-build/report.json`.

An initial attempt was skipped because Docker was stopped. After starting the installed
local Docker service, its credential helper stalled. That build was explicitly cancelled;
the successful build used an isolated empty authentication configuration to read public
images. No existing Docker credentials were read, edited or removed.

## Worker runtime

The newly built worker was run as its default unprivileged user with no network, a read-only
root filesystem and a temporary `/tmp` filesystem. Direct runtime probes verified:

- Installed certifi 2026.10.19, opentelemetry-api 1.45.1 and pypdf 6.21.1.
- Actual isolated extraction of the bundled four-page synthetic Kinsley Marrow PDF, including
  its expected customer text.
- The worker's Linux address-space limit rejected a 1 GiB allocation with `MemoryError`.
- The worker's Linux CPU limit terminated a busy loop with the expected limit signal.

These runtime probes cover the two platform-specific resource-limit paths skipped by the
macOS unit-test run. They are targeted probes, not a claim that the full Linux suite ran.
The probe container was removed automatically.

## Configuration

`make tf-validate` completed on the same committed source through the immutable gate context.
Terraform 1.16.4 validated ten configuration files using the pinned four-provider set.
Input SHA-256:
`28869cdca0e045e52af12d6e3318a2e470f0a6e70f40821a52b2940a0af07943`.
The initial format failure was fixed before the successful committed run. Initialization
used `-backend=false`; no plan, apply, cloud credentials or remote state operation occurred.

The checkpoint does not replace the remaining compose, baseline scan and disposable restore
checks, nor the remaining Reporting development. It is not a deployment or a declaration
that the repository's overall goal is complete.
