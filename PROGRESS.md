# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Review round-trip preserves draft work — October 15, 2026

- Added Back to field review with an in-memory draft snapshot. Continuing preserves unrelated
  human inputs and applies changed decisions to corresponding headers and source rows. Rejected
  source rows are removed; human-added rows remain. Renamed obligation keys are rebound explicitly
  when returning to the draft. No field decision is inferred from a changed draft value.
- Fixed row identity collisions when restoring deleted retained rows and when adding rows after
  reopening a draft with gaps in its local row identities. Tests exercise both failures plus
  field-review/form round trips and changed customer/amount decisions.
- 50 focused tests, frontend typing and full lint passed. Evidence:
  .run/ai-review-recovery-{tests,types,lint}.log. Recovery is local component state,
  not persistence across reloads or live browser/API acceptance evidence. Existing server version
  preconditions remain authoritative; returning to review captures the current displayed ETag
  only on explicit continuation. Broader release verification and accounting sign-off remain open.
  No deployment or live provider calls.

## Per-field review and confirmed draft handoff — October 15, 2026

- Added Accept/Edit/Reject controls, explicit low-confidence choices, edit/rejection reasons,
  citation checks and an explicit effective-date target. Decimal amounts remain strings;
  customer identity/code, entity, currency and quantities require normal draft inputs.
  Unsupported retained accounting terms stop continuation rather than being interpreted.
- Reused ordinary draft validation and inputs, then a separate confirmation sends atomic
  proposal acceptance with captured ETag, decisions and bindings. No activation action is
  offered. A failed request keeps the form; successful acceptance opens the draft workbench.
- 58 focused frontend review/upload/API/form tests, frontend typing and full lint passed. Logs:
  .run/ai-review-decisions-{tests,types,lint}.log. These are component/API-boundary checks,
  not a live browser/provider workflow or current full-release verification.
- Back-navigation to field choices, unsupported terms, DOCX, responsive tabs, full browser
  acceptance, broader release gates and independent accounting sign-off remain open.
  No deployment or provider calls.

## Review-source upload and resumable job navigation — October 15, 2026

- Added SF-20:new at /contracts/review/new, activating the existing Contracts entry. It validates
  nonempty PDFs up to 25 MiB, uploads ATTACHMENT, submits file_id, polls the returned AI_TASK and
  opens its retained proposal. A job URL resumes after reload, including after AI disable.
  Only the initiating human can cancel a running task. Failed/lost requests retain errors and
  retry keys; the successful upload is reused if extraction submission fails. Unrelated jobs
  and malformed result IDs cannot navigate. No entity or accounting values are inferred.
- Corrected a permission mismatch: ai.use now admits ATTACHMENT upload before a contract exists,
  without granting record-attachment or other-purpose writes. New API evidence checks upload,
  extraction admission and refusal of contract attachment/SSP upload. Existing no-upload tests
  now use a role without ai.use; request-attachment tests still refuse non-requesters and closed
  requests even when an AI source upload is permitted. Earlier logs preserve old-role assertion
  failures; the verified run passes all 25 extraction/file API tests.
- 30 frontend route/API/navigation checks, frontend typing and full lint passed. Local Chromium
  upload-to-job navigation with mocked HTTP returned no page errors; light/dark captures were
  inspected. This is not live API/provider or complete browser acceptance evidence. Logs:
  .run/ai-review-upload-{pg-verified,tests,types,python-types,lint,browser}.log.
- DOCX, field decisions, responsive panel tabs, draft-form integration, broad release verification
  and independent accounting sign-off remain open. No deployment or live provider calls.

## Contract review evidence screen — October 15, 2026

- Added SF-20 /contracts/review/:proposalId with permission-gated retained proposal/document
  reads, original text and field values, confidence/check indicators, accepted reviewer/time,
  recorded edited values/reasons and an accepted-draft link. Whole-proposal rejection requires
  a reason and the read ETag, preserves failure information, and refreshes retained evidence.
  Expired or missing-ETag proposals withhold rejection. Document failures offer reload.
- Citation spans must refer to the original file and fit the page. Highlighting uses Unicode code
  points to match Python offsets, never HTML, then focuses the highlight; Escape returns to the
  citation. Corrected focus handling so unrelated renders cannot steal focus back from a form.
- 19 route/API/permission checks, frontend typing and full lint passed. Local Chromium preview had no
  page errors and confirmed highlight/focus; light/dark 1440 and dark 1280 captures retained in
  .run/ai-review-screen-*.png. This preview mounts the component with cached synthetic responses,
  not the full shell or live backend. Logs: .run/ai-review-screen-{tests,types,browser,lint}.log.
- Upload/job navigation, field decisions, responsive panel tabs and draft-form integration remain
  unfinished. Broader release and independent accounting gates stay open. No deployment or live
  provider calls. The preview server was stopped after inspection.

## Retained acceptance reads and frontend API boundary — October 15, 2026

- Extraction detail/list now return accepted command/target, accepting human/time and recorded
  field decisions alongside unchanged original evidence. The fields remain protected by current
  source access. The worker-to-acceptance PostgreSQL witness compares detail and list results,
  reviewed values, actor and target; all seven acceptance/extraction/explanation API tests pass.
- Added a typed frontend API module for proposal pages/detail, document text, extraction
  submission, rejection and draft acceptance. It preserves server ETags, unmodified decimal
  strings/review bodies, shared command keys across lost responses, opaque cursors and API
  refusals. Retained reads require no AI-settings fetch; no automatic retries or draft inference.
  This is the API layer for SF-20, not a live screen. The route, field-decision controls and
  draft-form integration remain unbuilt.
- Six frontend API tests pass. Full backend typing passed 938 sources and focused typing passed
  789. Frontend typing initially caught omitted explicit default fields in the test draft; the
  fixture now supplies them. Full lint passed. Logs: .run/ai-review-client-tests.log and
  .run/ai-review-read-{pg,typecheck,focused-types,frontend-types,lint,openapi}.log.
  Broader release/accounting, structured-term conversion and browser gates remain open.
  No deployment or live provider calls.

## Worker-to-draft acceptance evidence — October 15, 2026

- Added an integrated PostgreSQL witness using the real four-page synthetic PDF, real PDF
  text extraction, queued AI_TASK dispatch and a deterministic provider response. It reads the
  worker's retained proposal/pages, edits the suggested customer to an explicit existing customer
  with a reason, and accepts through the public draft endpoint. Original content/citations and
  model-log linkage survive unchanged; the reviewed value is retained separately.
- A different authorized reader cannot see the unattached source/proposal, then can read the
  accepted proposal and identical retained pages through the new contract attachment. The draft
  carries AI_ASSISTED and provenance into its activation review basis, with no revenue posting
  and exactly one provider call. This does not prove browser review, independent activation,
  live-provider behavior or Linux parser isolation: the test uses the real in-process parser.
- Both acceptance tests passed, focused typing passed 789 sources and full lint passed. Logs:
  .run/ai-worker-acceptance-{verified,final-types,lint}.log. Earlier pg/pg-fixed logs retain test
  setup failures (missing retry callback and reused command idempotency key); verified is the
  corrected run. Broader release/accounting and structured-term gaps remain open. No deployment.

## Atomic reviewed extraction draft acceptance — October 15, 2026

- Enabled POST /ai/proposals/{id}/accept for new drafts, requiring explicit complete draft
  inputs, field decisions and supported header/line mappings. Fresh tenant customer resolution,
  human ai.use plus contract.create for the selected entity, source access, If-Match and exact
  expiry checks precede writes. At least one retained field is required. Cached replay also
  rechecks current permissions/source access.
- Normal contract creation, source-PDF attachment, combination suggestions, rule holds, accepted
  proposal provenance and audit commit in one transaction. Acceptance creates only a DRAFT;
  it does not submit activation or post revenue. Existing AI_ASSISTED activation controls apply.
  Retained review works with AI off. OpenAPI and frontend API types regenerated.
- PostgreSQL regression: 8 tests passed across acceptance, extraction/explanation submission,
  authorized lists and emergency disable. Acceptance covers competing reviewers (201/412),
  idempotent replay, no create permission, missing If-Match, exact expiry, mismatched amount,
  empty acceptance, injected rollback including attachment, one successful audit/provenance
  record, zero revenue postings and unavailable-source replay. The acceptance test seeds retained
  proposal evidence; it does not prove a full worker-to-activation or browser workflow.
- 98 unit/architecture checks and full lint passed; focused typing passed 789 sources. Logs: .run/ai-acceptance-{regression,final-types,
  final-unit,final-lint}.log. Structured-term mappings, existing-record acceptance approval,
  complete browser review, broad release verification and independent accounting sign-off remain
  open. No deployment or live provider calls.

## AI-assisted draft activation control — October 15, 2026

- Corrected the earlier acceptance prerequisite: PRD SM-11/BR-AI-05 permits a normal human command
  to create a new draft; AI_PROPOSAL_ACCEPTANCE applies to changes to existing records. New
  drafts instead require AI_ASSISTED activation review. The separate existing-record subject
  remains open, but is not a prerequisite for the new-draft acceptance route.
- Activation now derives AI_ASSISTED from immutable accepted extraction-to-contract links, so
  published auto-approval cannot bypass human review at any amount. Approval content includes
  provenance IDs, accepting human/time and a hash of field decisions, without quoted review text.
  Contracts without provenance retain their historical hash shape. Accepting humans are excluded
  from deciding activation, including via delegation, using the existing authorship mechanism.
- Verification: the PostgreSQL witness proves the AI-assisted contract waits under a published
  auto-approval rule, the ordinary control auto-approves, self-approval is refused and an
  independent reviewer can activate. The existing multi-flag activation regression also passed.
  A test assertion was updated for the expected MANUAL_ENTRY flag induced by human authorship.
  113 unit/layer/routing checks passed. Full typecheck passed (937 Python sources plus frontend),
  focused typing passed 788 sources, and final lint/diff checks passed. Logs:
  .run/ai-activation-provenance-{unit,verified,pg-final,typecheck,types-final,lint}.log. Full lint
  also passed. The pg-final
  log retains the earlier flag assertion failure; verified records its successful correction.
- New-draft acceptance still requires atomic command integration, source/expiry validation and
  structured-term handling. Broader release/accounting and list-performance gates remain open.
  No deployment or live provider calls.

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
