# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Extraction proposal rejection — October 15, 2026

- Extended POST /ai/proposals/{id}/reject to extraction evidence, sharing the existing reason,
  If-Match, idempotency and audit controls. Source authorization now runs in the review command's
  transaction; the proposal row is locked before checking version/status/expiry and transitioning.
  Current source access also gates cached command responses. Rejection preserves suggestions
  and citations, works with AI disabled, and does not call a provider or write accounting data.
- Verification: five PostgreSQL API tests passed, including extraction and narrative review.
  Two simultaneous extraction reviewers using the same ETag yield one 200 and one 412, with
  one audit event; exact expiry and terminal rows refuse rejection. Successful replay matches
  the first response, while replay after source shredding returns 404. Unauthorized reviewers
  cannot act; retained fields/citations and one provider usage record remain unchanged.
  Twenty-four architecture checks passed. Full typecheck passed (934 Python sources plus
  frontend), focused typing passed 786 sources, and OpenAPI/frontend artifacts were regenerated.
  Full lint and final diff checks passed.
  Logs: .run/ai-extraction-reject-{api,architecture,typecheck,types,openapi,lint}.log.
- Extraction list integration, per-field decisions and structured acceptance remain unfinished,
  alongside broader release/accounting gates. No deployment or live provider calls.

## Audited extraction document-text reads — October 15, 2026

- Implemented GET /ai/proposals/{id}/document-text for retained extraction evidence. Current
  source access is checked before the normal encrypted file reader rechecks ownership and
  commits a file.download audit as the human reader. The response preserves original pages and
  order with one-based page numbers. AI-off reads work; other kinds and shredded text return 404.
- Shared the canonical envelope decoder with worker persistence. Both paths validate exact
  source/job bindings; the public read additionally checks stored size/digest, while the decoder
  rejects malformed/noncanonical envelopes, wrong bindings, invalid page types and exceeded
  page/text limits. Reads neither parse the PDF nor call a provider.
- Verification: six PostgreSQL API/persistence tests passed, including AI-off text, actor audit,
  denied/unreadable sources, non-extraction proposals, shredded text/source and retained evidence
  rollback/regressions. Forty-one unit/architecture checks passed, including 17 text-envelope
  cases. Full lint/typecheck passed (934 Python sources plus frontend), focused typing passed
  787 sources, OpenAPI/frontend generation and final diff checks passed. Logs:
  .run/ai-document-text-{pg-final,unit,lint,typecheck,types-final,openapi}.log.
- Extraction list integration, human review/acceptance, broader release checks and independent
  accounting sign-off remain outstanding. No deployment or live provider calls.

## Authorized extraction proposal detail — October 15, 2026

- GET /ai/proposals/{id} now returns CONTRACT_EXTRACTION evidence as a distinct response shape
  alongside number explanations. Common actor/status/citation/ETag metadata is shared; extraction
  responses include source/text file IDs and the retained suggested-field array.
- The query selects binding metadata first, requires a current human ai.use grant and current
  original ATTACHMENT/PDF ownership access, and only then loads content/citations. Unreadable or
  shredded sources return 404. Reads work with AI disabled and neither decrypt text nor call a
  provider. Existing narrative source checks and narrative-only rejection/list paths are retained.
- Verification: five PostgreSQL API tests passed, including worker-produced evidence, AI-off
  reads, forbidden readers, another AI-enabled user without source access, missing/shredded
  sources and existing narrative list/rejection regressions. Twenty-four layer/file-access
  checks passed. Full lint and typecheck passed (933 Python sources plus frontend), focused
  typing passed 784 sources, OpenAPI/frontend regeneration and formatting/diff checks passed.
  Logs: .run/ai-extraction-read-{api,architecture,lint,typecheck,types-final,openapi}.log.
- Extraction list integration, original document-text responses, human review/acceptance and
  broader release/accounting verification remain open. No deployment or live provider calls.

## Authorized extraction submission API — October 15, 2026

- Added POST /ai/contract-extractions with file_id as its only input. It requires a human
  with ai.use, current access to an unshredded PDF attachment, enabled AI and text consent.
  The server pins the digest, fixed 507-field catalogue and 16000 output-token limit, returning
  an idempotent queued job with Location. HTTP performs no parsing or provider calls.
- Current file access is checked before replaying saved command responses. Admission shares
  the tenant lock with emergency disable; the worker independently rechecks access/settings.
  Added the request file binding and regenerated OpenAPI and frontend types.
- Verification: both extraction PostgreSQL API tests passed, including the actual queued worker
  with injected parser/provider, proposal persistence, replay after source unavailability,
  forbidden/hidden/missing/non-PDF inputs, text consent, rejected extra selectors and a proven
  database lock wait against disable. The three existing explanation API regressions passed.
  Twenty-two architecture checks, full lint, full typecheck (933 Python sources and frontend)
  and final focused typing (784 sources) passed. Test setup was corrected for registry timing,
  valid attachment types and the job registry's reserved engine release metadata.
  Logs: .run/ai-extraction-submit-{api-final-pass,api-verified,architecture,lint,typecheck,
  types-verified}.log. The combined api-verified log retains an earlier extraction assertion
  failure; api-final-pass verifies its correction. No live provider calls or deployment.
- Extraction proposal/document-text reads, human review/acceptance and broader release and
  independent accounting verification remain outstanding.

## Typed extraction field catalogue — October 15, 2026

- Defined the documented contract-review fields: seven header/review paths plus lines.0 through
  lines.499, matching contract line capacity. Queue and gateway selectors refuse other paths.
  Values require bounded nonblank text, exact ISO dates, positive whole JSON month counts and
  line objects containing only product_code and an exact signed decimal-string amount. Review
  terms remain text; no customer/product resolution, currency inference or accounting decision
  is made. The worker selector capacity now covers the full 507-path catalogue.
- Typed checks run on original parsed JSON before canonicalization: Decimal values would
  otherwise become strings and let a numeric money value masquerade as valid API-C-06 text.
  One invalid value refuses the whole proposal; rejected content is not retained. The documented
  four-page PDF fixture passes these field checks without changing its retained prompt bytes.
- Verification: 143 unit/architecture cases passed, including path/value boundaries, numeric
  money/coercion attacks, invalid dates, extra accounting fields and all catalogue selectors.
  Forty AI PostgreSQL cases passed, including the real worker, recovery and narrative regressions;
  unsupported selectors make no provider call and numeric amounts persist only an empty failed
  proposal. Full lint/typecheck passed (933 Python sources plus frontend), focused typing passed
  787 sources, and final formatting/diff checks passed. Logs:
  .run/ai-extraction-fields-{unit,pg,lint,typecheck,types}.log.
- Public submission, extraction review APIs, human conversion/acceptance and broader release and
  independent accounting verification remain unfinished. No deployment or live provider calls.

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
