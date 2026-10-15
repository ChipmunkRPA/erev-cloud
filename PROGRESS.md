# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Effective AI gateway settings — October 15, 2026

- Added an immutable settings snapshot from explicitly tenant-bound registry rows. All five
  values resolve from one version read at the aware job clock; only published/effective
  versions count. The snapshot retains source version IDs for later call evidence.
- Effective enablement requires an active workspace, published enablement, no immediate
  tenant turn-off and no platform kill switch. Model, sharing/redaction flags and monthly
  token budget are strict typed values; invalid values refuse without leaking their contents.
- Thirteen PostgreSQL cases cover defaults, draft/future versions, provenance, kill switch,
  immediate turn-off, suspended workspace, tenant isolation and malformed values. Combined
  AI/access/architecture checks: 185 passed, two Linux parser-limit tests skipped; strict
  API/test typing: 759 sources; Ruff passes. Final focused settings checks: 13 passed.
  Logs: .run/ai-settings-{checks,types,final-pg}.log.
- This reads the configured budget; it does not reserve tokens or enforce concurrency.
  Operational gateway execution, budget serialization, per-source permissions, attempt and
  proposal/audit persistence, settings command lifecycle and human acceptance remain open.
  No provider call or deployment; isolated test database stopped after verification.

## AI job initiator authorization — October 15, 2026

- Added current-grant authorization for a persisted AI_TASK attempt. It verifies the live
  job/task identity, requires the stored human creator to match the SYSTEM on-behalf-of id,
  and requires active user, workspace and membership before resolving permissions.
- The returned USER principal uses ai.use entity scope rather than SYSTEM's all-entity scope
  or the union from unrelated roles. It carries no recreated login or MFA evidence. Callers
  still owe per-file/report permissions and must use this narrowed context for retrieval.
- Eight PostgreSQL cases cover scoped access, revoked grants, suspended membership/workspace,
  disabled user, completed jobs, substituted initiators and inline/wrong-attempt refusal.
  Combined AI/architecture checks: 172 passed, two Linux parser-limit tests skipped;
  strict API/test typing: 758 sources; Ruff passes. Logs: .run/ai-access-{checks,types}.log.
- This is not an enabled AI_TASK handler. Gateway settings/kill-switch checks, budget
  serialization, authorized retrieval, durable attempt/proposal/audit writes and acceptance
  remain unfinished. The isolated local test database was stopped after verification.
  No deployment or production-readiness claim.

## PDF subprocess resource boundary — October 15, 2026

- Added the operational parser entry point as an isolated-interpreter subprocess with a
  minimal environment, closed inherited descriptors, discarded parser stderr and strict
  response validation. Text disablement and file caps refuse before child launch.
- The Linux child applies 512 MiB address-space and 15-second CPU limits before importing
  pypdf, and disallows core dumps/file writes through resource limits. The parent enforces
  30-second wall time; real-child testing confirms timeout kill/reap and secret removal.
  Unsupported hosts or unavailable resource limits fail closed, never parse in-process.
- AI/architecture checks: 180 passed, two Linux-only enforcement tests skipped on this Mac;
  strict API/test typing: 757 sources; Ruff passes. Logs: .run/ai-pdf-isolation-{checks,types}.log.
- Docker executable exists but its daemon cannot be reached. SUPERVISOR VERIFICATION NEEDED:
  Linux successful PDF parsing plus actual address-space/CPU exhaustion tests in the worker
  environment. These are not established by the local transport tests. No deployment.
- AI_TASK integration remains absent; the new subprocess entry point is not yet called by
  an enabled job. File authorization/storage, gateway budgets/auditing and acceptance remain open.

## PDF extraction and retained WLD-F-29 evidence — October 15, 2026

- Added pypdf 6.20.1 (BSD-3-Clause), worker-side PDF parsing and context-local stream/tree
  limits. Disabled text sharing refuses before parsing; files over 25 MiB, encrypted/invalid
  PDFs, more than 600 pages, over 2 MiB extracted UTF-8 text and textless documents refuse.
  Empty pages retain their numbering. Parser diagnostics are not returned as error details.
- Generated the four-page synthetic Kinsley Marrow order form and visually checked every
  page. A retained exact-input fake response now exercises all nine documented fields,
  confidences and three review flags through PDF parsing, preparation and citation validation.
  These checks create no proposal and apply no accounting fields or commands.
- AI/architecture/licence-unit checks: 154 passed (17.71s); strict API/test typing: 755 sources;
  Ruff and lock checks pass. Licence inventory: 142 packages, zero findings. Development
  dependency audit: all 86 pinned Python distributions and npm report zero vulnerabilities.
  Logs: .run/ai-pdf-{checks,types,licences,audit}.log; rendered pages: .run/ai-pdf-preview/.
- Worker process memory/time enforcement remains unverified: parser caps are not a process
  sandbox. Authorized reads, durable AI_DOCUMENT_TEXT files, job integration, budgets, audit
  writes and human acceptance remain open. No live provider call, deployment or readiness claim.

## Document preparation and citation binding — October 15, 2026

- Added extraction preparation over ordered worker-provided page text. Text sharing disabled
  refuses before page inspection; documents must have 1–600 pages and at most 2 MiB UTF-8
  text before and after redaction. Blank pages retain their original page numbers.
- The retained contract-review template, document UUID and allowed paths feed immutable
  request preparation. Exact outgoing page text is checked against retained redaction maps;
  any serialization/redaction mismatch refuses. Provider payloads exclude source mappings.
- A fake-provider integration check follows preparation through response validation and
  confirms that the cited amount addresses original source characters with low-confidence
  review still required. Tests also cover mutation, Unicode limits and redaction expansion.
- AI/privacy/architecture checks: 195 passed (16.54s); strict API/test typing: 753 sources;
  Ruff passes. Logs: .run/ai-document-preparation-{checks,types}.log.
- PDF extraction/worker limits, authorized file reads, durable text storage, operational
  gateway jobs/budgets/auditing and human acceptance remain open. This helper enables no
  route and makes no live call; no deployment or readiness claim.

## Retained contract-review prompt — October 15, 2026

- Added the versioned contract-review v1 file with id/version/purpose/output-schema front
  matter, citation rules and instructions to treat document text as untrusted evidence.
- A checked-in digest manifest and bounded loader require registered identifiers, exact file
  bytes and matching metadata. Changes require a new version; no latest-version fallback.
  The complete file is the system message, so preparation binds its full file digest.
- AI/architecture checks: 129 passed (12.01s); strict API/test typing: 752 sources; Ruff passes.
  Offline wheel build passed and packaged prompt bytes match the reviewed source exactly.
  Logs: .run/ai-templates-{checks,types,wheel,package}.log.
- This does not implement the gateway or complete AIX-3. Other prompt kinds, retained response
  fixtures, job authorization/budgets, audited attempt persistence and human acceptance remain
  open. No provider call or deployment; no production-readiness claim.

## Source citation offsets after redaction — October 14, 2026

- PRV-08 now exposes immutable substitution coordinates alongside its existing redacted
  text/counts. Email and international/local phone precedence stays shared with ordinary
  redaction. The mapping stores no removed contact values and stays outside provider input.
- Extraction validation can validate outgoing redacted pages and restore citations to source
  Unicode coordinates. Boundaries inside replacement placeholders refuse the entire proposal;
  complete placeholders map to complete source spans, subject to human viewing authorization.
- Privacy/extraction/architecture checks: 167 passed; strict API/test typing: 751 sources.
  Logs: .run/ai-offsets-checks.log and .run/ai-offsets-types.log. Ruff/formatting pass.
- The future gateway must retain the exact page mappings used for its prompt. Durable
  document extraction, authorized gateway jobs, value schemas, narrative-number checks,
  budgets, lifecycle auditing and human acceptance remain unfinished. No live calls/deployment.

## AI extraction output validation — October 14, 2026

- Added an atomic extraction validator: response digest/completion, strict JSON and unique
  allowed paths, confidence range, authorised document identity and Unicode page-span bounds.
  Low confidence below 0.75 is marked for review; no field is automatically accepted.
- Invalid fields refuse the entire proposal. Duplicate JSON keys, nonfinite numbers,
  oversized/deep responses and excessive decimal expansion refuse with safe error codes.
  Immutable canonical values preserve exact decimals without binary floating-point rounding.
- AI/provider/architecture checks: 128 passed; strict API/test typing: 750 sources.
  Evidence: .run/ai-extraction-validation.log and .run/ai-extraction-types.log.
- This helper is not connected to a gateway. Command-specific value schemas, redaction-offset
  mapping, semantic citation review, narrative-number checks, authorised jobs, budgets,
  persistence/auditing and human acceptance remain open. No live calls or deployment.

## AI request preparation boundary — October 14, 2026

- Moved provider contracts to domain ports, preserving adapter exports, so the forthcoming
  gateway can depend on the protocol without importing a network adapter.
- Added exact UTF-8 template digest checks and canonical request preparation. The explicit
  document-text argument requires opt-in; existing PRV-08 patterns redact values and system
  text. Contact-bearing field names are refused, not silently leaked or collapsed.
- Outgoing messages and configuration are immutable; the input digest binds template/version,
  actual message bytes, model, system text and generation/redaction settings. Floats are
  refused by canonical encoding. Callers still owe authorised, minimised input selection.
- Provider/preparation/configuration/privacy/architecture checks: 165 passed (23.21s).
  Strict API/test typing: 749 sources; Ruff/formatting pass. Evidence:
  .run/ai-preparation-checks.log and .run/ai-preparation-types.log.
- This is not an enabled gateway: job-only authorization, budget reservation, output
  validation, durable attempt/audit writes and human acceptance remain open. No live calls,
  deployment or readiness claim.

## AI SDK adapter and provider selection — October 14, 2026

- Added the official Anthropic SDK (locked 1.14.0), explicit vendor endpoint, 60-second
  timeout, no SDK retries and no SDK telemetry. Secrets resolve lazily through the scoped
  store. Text blocks, usage, model, stop reason, digest and monotonic latency are mapped;
  typed failures produce safe codes and retryability without provider response bodies.
- Tenant disablement/kill switch returns no provider; fake remains the test default.
  Selection constructs no client. All adapter tests use mocked clients; no live AI calls.
- Adapter/configuration/architecture checks: 110 passed; final adapter/configuration,
  licence and notices checks: 55 passed. Strict API/test typing: 747 sources; Ruff passes.
  Logs: .run/ai-sdk-checks.log, .run/ai-sdk-final.log, .run/ai-sdk-types.log.
  Final SDK network-boundary checks: 16 passed, .run/ai-sdk-network-final.log.
- Licence check: 141 packages, zero findings. Development dependency audit: zero Python
  vulnerabilities across all 85 pinned runtime distributions and zero npm advisories;
  .run/ai-sdk-licences.log and .run/ai-sdk-audit.log. Final clean-candidate audit still owed.
- Gateway/jobs, retained prompt fixtures, human acceptance and lifecycle auditing remain
  unfinished. SUPERVISOR VERIFICATION NEEDED: live Anthropic provider smoke test (not run;
  no live calls authorized here). No deployment or production-readiness claim.

## AI proposal evidence and state guards — October 14, 2026

- Migration 0148 adds T-AI-01, E-73/E-74 and the generated SM-11 transition guard.
  Content/citations and evidence links cannot change. Acceptance/rejection fields are
  set once, complete only in their matching state, and terminal records are frozen.
  Decisions must be a nonempty array; acceptance permissions and decision semantics
  still belong to the forthcoming human command. Expiry is explicitly supplied by its writer.
- Tenant-bound foreign keys reject another tenant's call log or document. Registered
  ORM, privacy, sandbox-regeneration, enum and isolation inventories; updated pinned head.
- Full migration round trip, DB lint, state/immutability/RLS, schema/privacy/snapshot
  and import-cycle checks: 140 passed; single-head check: 1 passed. Strict API/test typing
  passes (745 sources). Evidence: .run/ai-proposal-final.log, .run/ai-proposal-head.log,
  .run/ai-proposal-types.log. Provider/gateway, human acceptance and audit lifecycle
  remain incomplete; AI stays unavailable. No deployment or readiness claim.

## Immutable AI call evidence storage — October 14, 2026

- Migration 0147 adds T-AI-02 ai_model_log with tenant RLS, append-only grants and
  owner mutation guards. Provider/outcome values, SHA-256 digests and nonnegative
  token/latency counters are checked; raw prompt/response text has no column.
- Registered ORM, privacy classification, isolation row builder and sandbox treatment:
  call evidence stays with the source tenant and is regenerated in a sandbox.
- Corrected the migration test's old function count for the existing 0145 ownership
  trigger. API production plus new PG-test strict typing passes (744 sources); Ruff passes.
- Combined migration round trip, DB lint, immutability, RLS, schema/privacy/snapshot
  and import-cycle verification: 127 passed (31.44s), .run/ai-model-log-final.log.
  Typing evidence: .run/ai-model-log-types.log.
- Proposal table/transitions, gateway writes/audit facts and human acceptance remain
  unfinished. The AI lifecycle audit gap remains open; no AI enablement or deployment.

## AI provider foundation — October 14, 2026

- Implemented the DG §6.7 request/response protocol and deterministic FakeProvider.
  Exact input-hash fixtures precede version-local defaults; malformed exact fixtures fail
  without fallback. Digests cover exact UTF-8 response text; token/latency fields and path
  selectors are validated. No sockets, sleeps, accounting writes or external calls.
- Provider/configuration/architecture checks: 92 passed (20.88s); strict typing: three
  sources; Ruff/formatting pass. Evidence: .run/ai-provider-final.log and
  .run/ai-provider-types.log.
- AIX remains incomplete: provider selection/live adapter, retained fixtures, schema,
  gateway/jobs, human acceptance and audit lifecycle still required. No AI enablement,
  audit-category exemption, deployment or readiness claim.

## Reopening report verification — October 14, 2026

- Updated the lock/relock regression for required independently reviewed reopening evidence:
  preserve the hold/release versions, verify the billing version at the latest event date,
  and independently approve the specific late-event waiver through the normal API.
- The real re-close leaves September revenue and RPO unchanged, while contract balances
  reflect the invoice. All five report-figure cases pass (44.05s); strict test typing,
  Ruff and formatting pass. Evidence: .run/report-lock-recheck.log and .run/report-lock-types.log.
- AI audit coverage, other documented implementation gaps and full candidate verification
  remain open. No production-readiness claim or deployment.

## Migrated report catalogue verification — October 14, 2026

- Revalidated the remaining 12 integration failures on c8bc3fc: 10 passed, 2 failed
  (142.69s). AI audit lifecycle coverage and lock/relock version expectations remain open.
- Corrected the historical seed test to preserve migration 0048. The full migration-chain
  PostgreSQL comparison verifies all current catalogue fields; four catalogue checks pass
  (6.77s), Ruff/formatting pass. No historical migration changes.
- Evidence and remaining gaps: docs/release/CI-2026-10-14.md. No deployment or readiness claim.

## Full CI results and catalogue/isolation repairs — October 14, 2026

- Immutable 165d63c backend run finished in 5h 11m 13s: 10,843 passed, 33 failed,
  1 skipped, 3 xfailed, 640 deselected; CI failed at backend tests. This is an older snapshot.
  Full failure/revalidation inventory: docs/release/CI-2026-10-14.md.
- Reconciled privacy classifications with the current schema/native option terms; updated
  reviewed scope/lock/preview inventories and integration response fixtures, clarified guide
  API paths, and regenerated the frontend as-locked fixture from its API source.
- Downgrade tests start from fresh head. Reset disposes idle app/owner pools to prevent stale
  enum type OIDs after schema recreation; the checked-out database lock remains held.
- Final affected CI-unit recheck: 20 passed (13.61s); privacy/migration isolation suite:
  22 passed (35.33s); frontend as-locked checks: 90 passed (8.13s). Strict production/DB
  support typing (890 sources, explicit package bases) and Ruff pass.
- Remaining: historical report-seed equality, current-main revalidation of 12 other snapshot
  failures, AI audit coverage, lock/relock figure expectations, three expected-failure gaps,
  migration promotion and other release work. No deployment or readiness claim.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- SUPERVISOR VERIFICATION NEEDED: make audit-deps (October 14 development audit passed; rerun on a clean final candidate).
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
