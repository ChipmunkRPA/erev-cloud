# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Package synthetic AI evidence in runtime images — October 15, 2026

- API and worker builds now copy only the synthetic AI fixture bundle needed by FakeProvider.
  Previously local extraction tests passed but image inputs omitted the PDF and response files.
  A behavioral packaging regression reconstructs each Dockerfile's directory COPY inputs and
  invokes the provider from that isolated copy, checking a new upload ID and cited customer value.
- Seventeen packaging/PDF checks, focused typing, Ruff and full lint pass. Logs:
  .run/ai-image-fixtures-{tests,types,lint}.log. This is host-side copied-tree verification.
- Docker Desktop is now running. The first image build was deliberately interrupted to fix this
  packaging defect; Linux base-image pull session remains active, without a completed image.
  Container hardening, Linux PDF limits and full browser upload/acceptance remain unverified.
  Frozen CI on 3cf8f5b continues independently. No deployment or live provider calls.

## Source-page navigation for retained contract review — October 15, 2026

- The document pane now renders one selected source page instead of every page. The labelled
  selector is available for multipage documents; citations select their page and focus its
  highlight. Manual navigation clears the old highlight without changing field decisions.
- Twelve route tests and a cached-data Chromium probe cover page navigation, citation jumps,
  Escape focus and retained edits. Screenshots inspected at 1280/1440 px. Logs:
  .run/ai-review-pages-{tests,types-final,lint,browser}.log. Frontend typing and full lint pass;
  the initial type-check caught two Field API mistakes corrected before the final run.
- Updated release limitations for the responsive panes and page navigation. Full release evidence,
  live browser acceptance and independent accounting sign-off remain outstanding. Frozen CI on
  3cf8f5b is still live; Docker daemon remains unavailable. No deployment or live provider calls.

## Responsive contract review panes — October 15, 2026

- SF-20 now uses Document / Proposed fields panel tabs below 1440 px and two columns above,
  with pane=document|fields in the URL. Field decisions, edited values and reasons survive pane
  and viewport changes. Citations open Document and focus the source highlight; Escape waits
  for the fields pane to become visible before returning focus to the originating citation.
- 24 focused review/decision/tab tests, frontend type checking and full lint pass. A cached-data
  Chromium preview verifies citation/Escape focus and retained edits at 768/1280/1440 px;
  screenshots inspected. Logs: .run/ai-review-panes-{tests,types,lint,browser}.log.
- This browser witness uses retained synthetic data, not a live upload-to-acceptance workflow.
  Full frozen CI on 3cf8f5b remains active; repository readiness and accounting sign-off remain open.

## Bundled extraction fixture through upload and draft acceptance — October 15, 2026

- Strengthened the worker/acceptance witness: source now enters through POST /files and the
  configured fake provider serves the complete nine-field bundled document fixture, replacing
  the test-only one-field provider. The uploaded ID is checked in every citation. Explicit human
  customer/product edits, accepted date/payment terms and rejected terms/second line are recorded
  separately from unchanged original evidence. Persisted booking values, attachment-based access,
  AI_ASSISTED review provenance, one provider call and zero revenue postings are asserted.
- Both acceptance regressions pass on isolated PostgreSQL 55441, with focused strict typing
  (791 sources), Ruff and full lint. Logs: .run/ai-bundled-acceptance-{final,types,lint}.log.
  Earlier attempts retain two corrected fixture assumptions: the test tenant uses a different
  product code, and stored ACCEPT decisions also snapshot their accepted values.
- This is API/worker/database evidence using an in-process PDF parser, not browser interaction,
  Linux isolation, live-model accuracy or independent activation/accounting sign-off. Demo/browser
  fixture setup remains unfinished. Frozen CI on 3cf8f5b remains live on separate PostgreSQL 55439.
  No deployment or live provider calls.

## Repair AI lifecycle audit references and worker inventories — October 15, 2026

- Narrative rejection and expiry now pass distinct source contract IDs to the audit writer
  inside their tenant transaction; missing source contracts refuse rather than writing an
  unlinked event. Extraction creation/rejection explicitly names no pre-existing draft contract.
  Database tests verify hashed detail, the contract audit index, rollback and retained evidence.
- Reviewed expiry's limited tenant-directory read and bounded tenant SYSTEM transitions; added
  the reasons to TXN-07 and caller inventories. Removed the implemented AI_TASK from the pending
  registry while preserving detector checks for omissions, duplication and wrong build phases.
- 24 targeted architecture checks, eight PostgreSQL lifecycle/API checks, strict typing (793
  sources) and full lint pass. Separate cross-tenant source check: .run/ai-audit-keys-tenant-check.log.
  PostgreSQL verification ran on a new isolated instance at 55441; initial encoding setup errors
  are retained separately from the verified UTF-8 run. Logs: .run/ai-audit-architecture.log and
  .run/ai-audit-keys-{pg-verified,types,lint}.log. See docs/release/CI-2026-10-15.md.
- The full frozen CI on 3cf8f5b remains live on 55439 and predates these repairs. No restart,
  deployment or live model call. Browser fixtures/acceptance, remaining implementation and release
  gates, and independent accounting sign-off remain open.

## Bind the known extraction fixture to real upload requests — October 15, 2026

- Found that the bundled fake extraction response matched only its original fixed document ID,
  model and nine-path request. Real upload IDs/full worker catalogues had no fixture. Added a
  bundled-only fallback that reconstructs the complete known redacted-document request before
  reusing retained values, filtering allowed fields and rebinding citations to the upload ID.
  Arbitrary source text, prompts and inconsistent hashes still fail. Custom fixture roots retain
  exact/default semantics. No network calls or accounting writes are introduced.
- AI unit suite: 250 passed, two Linux resource checks skipped on macOS. Focused strict typing
  passes 790 sources; full lint passes. Evidence: .run/ai-upload-fixture-first-failure.log (completed unit run),
  .run/ai-upload-fixture-types.log. Combined AI/architecture run: 508 passed, 12 failed,
  two skipped in .run/ai-upload-fixture-tests.log. Failures identify existing AI audit writers
  without contract keys, unlisted expiry SYSTEM/platform-directory callers and AI_TASK still
  marked pending after registration. No broad pass is claimed; these require follow-up repair.
- Full frozen CI remains live on 3cf8f5b against isolated PostgreSQL 55439, in engine tests.
  Do not restart it or run other database tests there. Known-document fixture adaptation does
  not complete demo/browser seeding, Linux parser proof, browser acceptance or accounting sign-off.
  No deployment or live provider calls.

## Broad frontend verification and frozen CI — October 15, 2026

- Full frontend testing found two inventory failures: omitted SF-20 route IDs and no crawl
  proposal lookup. Added both without a skip/exclusion; a live crawl still requires accessible
  retained extraction evidence. The repaired full suite passes 2,143 tests in 200 files.
  Frontend typing, focused ESLint and formatting pass. Evidence and limits:
  docs/release/CI-2026-10-15.md; .run/frontend-full-oct15-repaired.{log,xml}.
- Frozen make ci on 3cf8f5b has passed environment, full lint and typecheck (938 Python files)
  and is running the broad test stage against isolated local PostgreSQL 55439. Live log:
  .run/production-readiness-ci-oct15.log. Do not restart the live run. This snapshot predates
  the inventory repair; its eventual results must remain attributed to that snapshot.
- No full CI pass is claimed. Real retained-proposal browser fixtures, complete acceptance,
  broader release gates and accounting sign-off remain open. No deployment/provider calls.

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
