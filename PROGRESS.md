# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Extraction gateway and worker dispatch — October 15, 2026

- Connected extraction execution to fresh human/source/settings admission, the tenant budget
  lease, committed text/call intent, audited outcomes and proposal persistence. Retries reuse
  retained input without reparsing, observe durable 5/10-second backoff and stop at three calls.
  Permanent/exhausted errors finalize against the last log. Completed replay makes no new call;
  uncertain outcomes/usage block execution. Mid-call disable/revocation retains usage without
  creating a proposal. Cancelling an uncertain job preserves its evidence and budget hold.
- AI_TASK now validates narrative or extraction selectors, rejecting prompts/model/text input.
  The worker composition root supplies the isolated PDF parser and lazy provider. Worker retry
  count remains one; the gateway owns provider attempts. Human review/acceptance remains separate.
- Verification: 38 AI PostgreSQL cases passed, including a real queued extraction job, interrupted
  wait/failure recovery, lease release across waits, exact retained requests, cancellation,
  disabled/text-off/budget admission, invalid output and known/unknown usage. Three final cases
  passed after the uncertain-call cancellation correction. Thirty-nine dispatch/layer checks
  and nine worker/probe checks passed. Full lint/typecheck passed (932 Python sources plus
  frontend); final focused typing passed 784 sources and final formatting/lint checks passed.
  Logs: .run/ai-extraction-gateway-{pg-fixed,regressions,final-pg,unit,worker-unit,lint,
  typecheck-last,types-last}.log. An initial test-only mappingproxy serialization mistake and
  two strict-typing issues were corrected. Fake providers/parsers only; no deployment/live AI.
- Public extraction submission, approved field catalogue, document-text/proposal review APIs,
  human acceptance and broader release/accounting gates remain unfinished. Linux parser resource
  enforcement and live-provider operation are not proved by these local worker tests.

## Extraction recovery from retained input — October 15, 2026

- Added a worker-only recovery reader that freshly authorizes the initiating human, selects
  call/proposal binding metadata, and rebuilds exact request bytes/citation maps from encrypted
  intent-linked text. It validates source access, digests, field paths and original model/prompt
  settings. It does not reparse a PDF or invoke a provider. Existing proposals return their ID;
  recorded failures return validated classification, usage, attempt number and outcome time for
  gateway backoff. Missing outcomes and unclassified results refuse automatic recovery.
- Evidence reads work while new AI calls are disabled, but current permission revocation refuses
  recovery. Tests cover completed proposals, reported/unknown provider usage, changed selectors,
  mismatched source fingerprints, no outcome, invalidated responses and unchanged call/log counts.
  Shared retained-page validation also continues to serve proposal writes.
- Verification: 21 AI PostgreSQL regressions passed; the final focused case passed after narrowing
  proposal queries to binding metadata. Thirty preparation/layer tests passed. Full lint and
  typecheck passed (931 Python sources plus frontend); final focused typing passed 782 sources.
  Logs: .run/ai-extraction-recovery-{pg,regressions,pg-final,unit,lint,typecheck,
  types-verified}.log. No deployment or live provider calls.
- Gateway admission, retry execution, worker dispatch, submission and human acceptance remain
  unfinished. This reader supplies recovery evidence; it does not authorize another provider call.
  Broader release verification and independent accounting sign-off remain outstanding.

## Durable extraction call document links — October 15, 2026

- Migration 0155 adds paired source/text file references to immutable AI call intents, with
  tenant-bound foreign keys and a downgrade guard against losing populated links. A worker can
  locate exact retained text through the committed call before any proposal exists. Intent
  writers validate paired purposes and unshredded files; retries preserve both links. Extraction
  success/failure persistence verifies its file IDs against the call intent.
- Both references now hold evidence independently of proposal creation or outcome. They grant
  no extra read access. Direct shred is refused; existing independently reviewed EVIDENCE_SHRED
  can lift the holds and destroy the text key, preserving immutable references and digests.
- Verification: 29 PostgreSQL migration/AI regressions passed, including full migration round
  trip, tenant FK/null-pair checks, immutable intent and lossy downgrade guards. Three final
  cases passed for extraction retry-link rejection and proposal/call-only reviewed erasure.
  The latter prove direct refusal, independent approval, key destruction and failed decrypted
  reads after erasure. Thirty-two architecture/unit checks passed. Full lint/typecheck passed
  (930 Python sources plus frontend); focused typing passed 782 and erasure typing 781 sources.
  Logs: .run/ai-intent-documents-{pg,erasure-pg,unit,access,lint,typecheck,types-final,
  erasure-types}.log. No deployment or live provider calls.
- This closes a prerequisite discovered at gateway integration: call evidence previously could
  not locate or protect retained text before proposal persistence. Extraction execution/recovery,
  submission and human review remain unfinished, alongside the broader release/accounting gates.

## Extraction provider-failure evidence — October 15, 2026

- Added terminal extraction failure persistence using the existing committed attempt log.
  It rebuilds retained document evidence, validates request/provider/error metadata and the
  initiating human/job intent, then writes a failed proposal with empty content/citations.
  It neither duplicates the attempt nor changes its reported/unknown usage. Narrative failures
  share the evidence validator; extraction additionally requires a call intent.
- Verification: 21 AI PostgreSQL cases passed, including narrative retries and extraction
  failure/rollback. The final focused extraction case also passed after adding missing-intent
  refusal and explicitly binding test-loop captures. Tests cover timeout with unknown usage,
  permission failure with reported usage, unchanged log bytes/metadata, wrong error codes,
  unrelated response logs, no intent, rollback and audit attribution. Seventeen architecture
  checks passed. Full lint/typecheck passed (929 Python sources plus frontend); final focused
  typing passed 780 sources. Logs: .run/ai-extraction-failure-{pg,pg-final,layers,lint,
  types-final,typecheck}.log.
- The gateway still owns admission and retry exhaustion. Extraction dispatch, provider recovery,
  submission, review/acceptance and the broader release/accounting gates remain unfinished.
  No deployment or live provider call; no production-readiness claim.

## Encrypted extraction proposal evidence — October 15, 2026

- Added a persistence component for original document pages and received extraction responses.
  Text is encrypted per file and bound to the source digest, human and running AI job; repeated
  retention for that job reuses the same file. Saving a proposal rebuilds the request and citation
  mappings from retained bytes, checks the call intent and records usage, content and audit
  evidence atomically. Refused, invalid or uncited responses become failed proposals without
  retaining rejected provider text. Shared job/intent binding checks also serve narratives.
- Verification: 20 existing AI database cases passed in the broader run; its new case exposed
  a missing test-helper argument, now fixed. The final focused PostgreSQL case passed, covering
  ciphertext, original citation offsets, low confidence, refusals, cross-job text/intent swaps,
  changed request fields, missing permission, deduplication, rollback and human audit attribution.
  71 preparation/validation/layer tests passed. Strict focused typing passed 780 sources; full
  typecheck passed 929 Python sources plus frontend. Full lint passed. Logs:
  .run/ai-extraction-persistence-{regressions,pg-final,unit,types-final,typecheck,lint}.log.
- Extraction dispatch, budget/provider recovery, submission, field schemas and human acceptance
  remain open. These components do not invoke a provider or apply accounting changes. Broader
  release verification and independent accounting sign-off remain outstanding. No deployment.

## Authorized extraction input preparation — October 15, 2026

- Added a worker-only document retrieval component: reauthorize the current human and attempt,
  require enabled AI and text consent, bind a readable ATTACHMENT/PDF source, enforce its size
  and hash, and audit decrypted reads as the human. An injected isolated parser runs outside
  SQL sessions; heartbeats and fresh admission afterward check cancellation, grants, settings
  and source access before redacted request preparation. Original pages/citation mappings stay
  local. The PDF byte limit is shared with the adapter; cancellation guard exports stay compatible.
- This component does not call a provider, reserve tokens or create a proposal. Extraction
  dispatch, durable encrypted text, provider recovery, proposal persistence and submission still
  need integration. No accounting command or automatic field application was introduced.
- Verification: 20 AI database regressions passed, plus the final focused expiry case. The new
  test reads an encrypted fixture through the file service, checks disabled/text-off/hash/access
  refusals, user download audits, redaction, disable/revocation during parsing and cancellation.
  52 parser/preparation/layer cases passed; two Linux resource-limit cases skipped on this Mac.
  Full lint and typecheck passed (928 Python sources plus frontend); focused typing passed 780
  sources. Logs: .run/ai-document-read-{regressions-final,expiry-final,unit,lint,typecheck,
  types-verified}.log. A nullable tenant-kind read was tightened to scalar_one for typing.
- The broader run exposed a prior expiry test counting other committed tenants. Local exact
  assertions now name its tenant; global fan-out and repeat-run checks remain, with exact audit
  checks for its proposals. Production expiry code was unchanged. No deployment/live AI calls.

## Authorized AI proposal list — October 15, 2026

- Added GET /ai/proposals for supported number explanations using API-C-09 cursor pagination,
  kind/status filters, optional totals and id/created_at sorts (default newest created_at,
  then descending id). The SQL source-authorization predicate is shared with detail/rejection;
  hidden and unsupported proposals cannot occupy page rows or inflate counts.
- Every page checks current overlapping ai.use/contract.read grants. Tests cover foreign and
  out-of-scope cursor reuse, and the same user's scope narrowing between pages. Unsupported
  kinds return empty results until their source authorization is implemented.
- Verification: three API database cases passed after the final change, covering submission,
  reads, rejection and listing; 25 route/layer checks passed. Full lint, OpenAPI generation and
  typecheck passed (927 Python sources plus frontend); focused typing passed 778 sources.
  Logs: .run/ai-list-{api-final,architecture,openapi,typecheck,types-final,lint}.log. A row mapping
  is copied to a dictionary at the shared serializer boundary to satisfy strict typing.
- Acceptance, extraction, anomaly summaries, Q&A and broader release/accounting requirements
  remain open. No deployment or live provider calls; no production-readiness claim.

## Scheduled AI proposal expiry — October 15, 2026

- Wired SCH-11 into the worker at 03:20 UTC daily. Each tenant is processed in batches of
  at most 100 locked rows; concurrent review locks are skipped for a later sweep. Only due
  proposed rows become expired, with a row-version increment and SYSTEM audit in one transaction.
  Content, citations, call logs, files and terminal proposal states remain intact; AI switches
  do not govern maintenance. Existing rejection checks enforce expiry between daily sweeps.
- Migration 0154 adds the tenant/expiry/id index. The application-role EXPLAIN test proves
  expires_at bounds the expiry query under RLS; migration upgrade/downgrade/upgrade checks pass.
- Verification: eight PostgreSQL migration/index cases, the real proposal lifecycle case on
  the new head, and 22 worker/layer checks passed. The lifecycle checks the boundary, newer and
  terminal rows, two tenants, review locks, interrupted-batch rollback, multi-batch expiry,
  repeat runs, audit cardinality and retained reads. Full lint and typecheck passed (926 Python
  sources plus frontend); focused typing passed 780 sources. Logs:
  .run/ai-expiry-{head-pg,migrations,unit,typecheck,types-verified,lint-final}.log.
  Initial fixtures were corrected to provision a real second tenant and import the transition
  helper directly for strict typing. No production code was loosened for those fixes.
- Listing, acceptance, extraction and other AI operations remain open, along with the broader
  accounting/verification backlog and independent sign-off. No deployment or live AI calls.

## Number-explanation rejection — October 15, 2026

- Added POST /ai/proposals/{id}/reject for supported number explanations. A human with current
  source access supplies a nonblank reason and current If-Match ETag. The locked transition
  records reviewer/time/reason, increments row version and audits once in the same transaction.
  Expired or terminal items cannot be rejected. No provider or accounting command is called.
- Source permission intersection is explicit in SQL inside the existing command transaction.
  A source-access dependency runs before idempotency replay, preventing cached content from
  bypassing later scope restrictions. Rejection remains available while AI is disabled.
- Verification: all 19 AI domain regressions passed; both final API cases passed, including
  overlapping permissions, expiry boundary, simultaneous reviewers (200/412), replay, narrowing
  access after success, reason/precondition validation and one human audit event. 54 unit/layer
  checks and 25 final route/layer checks passed. OpenAPI generation, full typecheck (925 Python
  sources plus frontend), focused typing (776 sources), and lint passed. Logs:
  .run/ai-reject-{regressions,api-verified,unit,architecture-final,openapi-final,typecheck,
  types-verified,lint-final}.log. Early tests caught a missing row-version increment; corrected.
  Expiry and revocation fixtures were corrected to use the UOW clock and revocation metadata.
- Acceptance, extraction review, other proposal kinds, listing, expiry processing and broader
  release gates remain open. No deployment or live provider calls; no production sign-off.

## Retained number-explanation reads — October 15, 2026

- Added GET /ai/proposals/{id} for NUMBER_EXPLANATION evidence with content/citations,
  status, actors and ETag. Current ai.use/contract.read grants are intersected; reads require
  a visible current or past member contract of the retained trace's group. Unsupported kinds
  fail closed. AI switches do not prevent authorized evidence reads or trigger provider calls.
- Calculation traces have tenant-only RLS, so a trace join alone does not authorize entity
  access. Added explicit member visibility to proposal reads and completed-job recovery.
- Verification: 21 AI/API database regressions and 54 unit/route/layer checks passed. API cases
  cover content, cross-tenant and entity refusal, revoked grants, peer reads and both AI switches.
  Full lint, OpenAPI generation and typecheck passed (925 Python sources plus frontend).
  Focused strict typing passed 776 sources. Logs: .run/ai-proposal-read-{regressions,unit,lint,
  openapi,typecheck,types}.log. An initial test used a nonexistent disable-reason field; corrected
  to the actual actor-kind column before the passing database run.
- Listing, other proposal kinds, review commands and broader release gates remain open.
  No deployment or live provider calls; this is development evidence, not production sign-off.

## Number-explanation submission — October 15, 2026

- Added POST /ai/explanations for the number-explanation form: 202 API-S-Job with Location,
  normal idempotency and the initiating human. HTTP validates source access through overlapping
  ai.use/contract.read scope and the shared narrative read path, but makes no provider call.
- Queue insertion and AI switch admission share the tenant lock. A concurrent disable completes
  before a waiting submission can proceed, causing ai-disabled with no new job. New jobs retain
  selectors, a validated trace ID and a 2048 output-token limit; prompts/model settings are not
  queued. The worker rejects a changed trace before calling; old unbound fingerprints are intact.
- Verification: 21 AI/API database cases passed, followed by both final API cases (including
  real lock contention, idempotency, scope refusal, HTTP-to-worker persistence and changed-trace
  refusal). 40 unit/route/layer checks passed. Full lint, OpenAPI generation and full typecheck
  passed (924 Python sources plus frontend); focused strict typing passed 775 sources. Logs:
  .run/ai-submission-{regressions,api-final,unit,lint,openapi,typecheck,types-final}.log.
- The initial permission fixture was corrected to use an auditor without ai.use; test import
  typing was corrected before the final checks. Anomaly/extraction/Q&A submission, proposal
  read/review and durable AI admission-failure evidence remain open. No deployment/live calls.

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
