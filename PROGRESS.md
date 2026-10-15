# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Explicit extraction header bindings — October 15, 2026

- Added combined draft review for retained customer name, effective date and payment terms,
  alongside the existing line checks. The reviewer explicitly maps an effective date to draft
  inception or signature; payment terms and the selected date must match exactly. Customer
  names match either the explicit inline reference or a resolved ID/name whose ID equals the
  draft's selected customer. No name search, date inference or accounting classification occurs.
- Every retained header must have an implemented mapping; rejected headers cannot be mapped.
  Term months, termination, variable-consideration terms and material-right text currently refuse
  combined review rather than disappearing silently. Existing customer resolution must still be
  wired to fresh tenant-authorized reads in the eventual acceptance command. Approval, structured
  term mappings and atomic persistence remain unfinished; acceptance is not enabled.
- Verification: 91 unit/layer cases passed, including 15 new header tests. A final 39-case draft
  suite passed after a typing-only iteration correction. Cases include explicit date meaning,
  missing/mismatched dates and payment terms, exact inline/resolved customer identity, rejected
  or unbound headers, unsupported structured terms and JSON round-trip with omitted replacement
  values preserved. Focused typing passed 788 sources. Logs:
  .run/ai-draft-headers-{unit,final,types-final,typecheck,lint}.log. Full lint and typecheck
  passed (936 Python sources plus frontend), as did final formatting/lint/diff checks.
- Broader release/accounting and list-performance gates remain open. No deployment or live
  provider calls.

## Explicit extraction draft inputs and line bindings — October 15, 2026

- Added draft-intake preparation using the existing ContractCreateIn schema, explicit entity,
  field decisions and line_bindings from retained paths to obligation keys. Entity codes must
  agree, activation is forbidden, mapping targets must exist and be unique, and every retained
  line must map exactly once. Rejected lines cannot be mapped. Mapped product and exact amount
  must agree with reviewed values, and line currency must match the explicit draft currency.
- Required contract identity, currency, quantities and obligation keys come from human input;
  no source value fills missing fields. Additional human-authored lines remain possible. This
  is not an acceptance endpoint. Header/customer/structured-term binding, the pending approval
  subject AI_PROPOSAL_ACCEPTANCE, command authorization/expiry/SoD and atomic persistence remain.
- Verification: 76 unit/layer tests passed, including 24 new draft cases, 35 field-review cases
  and 17 architecture checks. Tests cover required inputs, entity/activation/command refusals,
  mapping coverage/uniqueness, product/sign/amount/currency mismatches, edit consistency and
  rejected lines. Initial fixture/scalar comparisons were corrected to use API-S-Money objects
  and decimal-string quantities; guards were retained. Full typecheck passed (936 Python sources
  plus frontend), focused typing passed 788 sources and final formatting/lint/diff checks passed.
  Full lint also passed. Logs: .run/ai-draft-review-{verified,typecheck,types-final,lint}.log.
- Broader release/accounting verification and large-tenant list performance remain open. No
  deployment or live provider calls; the acceptance route remains disabled.

## Explicit extraction field-review decisions — October 15, 2026

- Added the ACCEPT/EDIT/REJECT request item schema and pure review resolver. Every retained path
  must appear exactly once; invalid originals, missing/duplicate/unknown paths and oversized
  reviews refuse. EDIT explicitly supplies a typed value; ACCEPT/REJECT cannot hide replacement
  values. EDIT/REJECT require bounded nonblank reasons. Accepted values retain exact types and
  decimal-string representation, edits use the field catalogue, and rejections leave fields unset.
- Resolved values and decision records are detached copies in proposal order. Rejecting every
  field produces no defaults. This component does not write contracts or enable acceptance;
  conversion still requires explicit contract identity, currency, quantities, obligation keys
  and structured terms, with command-level source/permission/status/expiry/SoD and atomicity.
- Verification: 35 final unit cases passed, covering full 507-field capacity, overflow, exact
  coverage, malformed reasons, forbidden replacements, invalid dates/months/numeric money,
  invalid retained values, all-rejected reviews and detached mutable inputs. Seventeen layer
  checks also passed in the initial 50-case run. Full lint/typecheck passed (935 Python sources
  plus frontend), final focused typing passed 786 sources and final formatting/lint/diff checks
  passed. Logs: .run/ai-field-review-{unit,boundaries,lint,typecheck,types-final}.log.
- Structured acceptance remains unimplemented; broader release/accounting and large-tenant list
  performance gates remain open. No deployment or live provider calls.

## Authorized extraction review list — October 15, 2026

- GET /ai/proposals now includes extraction evidence alongside number explanations, with the
  shared kind/status filters, authorized totals and stable cursor pagination. Extraction source
  metadata is checked through the existing file ownership rules before SQL paging/counting or
  selecting proposal content. Shredded/non-PDF sources and unsupported kinds cannot enter results.
- Only distinct referenced source-file metadata is scanned, in batches; readable UUIDs use one
  array parameter. This preserves uploader/shared-upload and attachment access semantics but
  still performs per-source authorization work. Large-tenant latency/load verification and
  optimization remain outstanding. Missing contract.read grants exclude narrative evidence
  without preventing otherwise authorized extraction reads.
- Verification: five PostgreSQL API cases passed, covering extraction inclusion, exact counts,
  kind/status filters, denied source owners, disappearance after shredding, and narrative cursor,
  grant-narrowing and review regressions. Twenty-eight architecture/list-contract checks passed.
  Full typecheck passed (934 Python sources plus frontend), focused typing passed 786 sources,
  and OpenAPI/frontend generation passed. Logs:
  .run/ai-extraction-list-{api,architecture,typecheck,types-final,openapi,lint}.log.
  Full lint and final diff checks also passed.
- Per-field decisions, structured acceptance and broader release/accounting verification remain
  open. No deployment or live provider calls.

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
