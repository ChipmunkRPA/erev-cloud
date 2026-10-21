# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Current owner-authorized goal — October 21, 2026

Finish the repository for public source publication under its noncommercial license;
prioritize feature completion with necessary targeted validation. Continue directly on main,
review and publish changes without PR accumulation, and do not deploy.

- Reporting priorities remain difference attribution, multi-currency, RPO exemptions and GL
  reconciliation. Combined contracts now retain original receiving-contract aging and separately
  show member allocation adjustments; continue the remaining evidenced Reporting gaps.
- Migration-to-live promotion/replay completion is outside scope; no actual business launch.
- Keep key financial permissions, segregation of duties and audit evidence; full approval
  coverage is not required. Implementation is not a SOX certification.
- Sandbox goal: refresh from production and allow experimentation isolated from production.
  Reproduction of production lock history and sandbox locking are not completion requirements.
- Independent accounting review belongs to the owner and is not a development completion gate.
- Owner resumed development October 21. The app goal tool cannot edit the existing objective
  text; this section records the superseding scope while the goal remains active.

## Book Bridge same-source rebuild — October 21, 2026

- New runs retain the pre-aggregation per-contract amounts for both books, the selected currency
  basis and consumed driver facts. A same-source rerun rebuilds all three sections, counts,
  totals and the driver tie-out from those inputs without reading current contract labels,
  book configuration, balances or FX rates. Workspace/entity and currency-view checks remain.
- The registered source strategy is retained_inputs; older OPEN runs preserve their original
  new-evaluation semantics. Migration 0295 describes retained inputs and the reporting FX tables.
- Necessary verification passed: a later GBP bill/recomputation changes the live reporting-view
  balances while the original public rerun keeps its rows and output hash; input-only rebuild
  recomputes driver totals without a session and rejects scope/view mismatch; catalogue parity,
  40 focused builder/source-binding tests and scoped lint/types pass. No deployment.
- Causal attribution remains unfinished: the existing collectibility/reversal flags do not
  isolate simultaneous effects, and framework/licence/advance-FX residuals require counterfactual
  computation. The engine exposes resolved BookInput policies and original computation evidence;
  the close-variance worker already separates authorized input reads from SQL-free engine runs.
  Extend that pattern for book-policy phases, verify original book endpoints, and preserve any
  unreproduced residual rather than labelling an entire difference from a historical event flag.
- Also remaining: Adoption Bridge currency support, Intercompany Pairs retained input replay
  and residual attribution, other documented adapters and final repository validation.

## Intercompany Pairs functional and reporting currencies — October 21, 2026

- Functional view now reads the posted functional amount/currency of each entity's lines.
  Different functional currencies remain separate: an incomparable counterpart and unmatched
  amount are empty, not zero or a false break. Contract-detail keys distinguish split currency
  and entity-pair rows without changing existing unambiguous transaction-view keys.
- Reporting view translates each entity's posted period activity using the approved period
  average into the tenant reporting currency, with rate/version/cutoff evidence. This is the
  existing period-activity report, not a new cumulative closing-balance report. Translation
  residuals remain visible and can fail the tie-out; no artificial elimination is inserted.
- Necessary validation passed: public K04 transaction and functional/reporting runs, comparison
  to posted USD due-from amounts and GBP due-to translated at September 1.28, single-entity
  permission scope, existing CSV/XLSX/PDF output, seven focused row/tie-out tests, migration
  0294 catalogue parity and scoped lint/types. No deployment.
- Remaining: Intercompany Pairs same-source retention and finer residual attribution; Adoption
  Bridge is explicitly transaction-only and needs a separate cumulative adoption-date currency
  design. Book Bridge granular causal attribution/retention and other documented Reporting
  gaps remain open. This feature does not claim overall repository completion.

## Book Bridge reporting-currency view — October 21, 2026

- Reporting view now translates each contract/book/period's posted functional revenue using
  its approved period-average rate, then aggregates the range. Ending functional member
  balances use the final period closing rate. Both books share the same target currency and
  rate basis; historical functional layers are projected before reporting translation.
- Rate IDs, versions, period and cutoff are recorded through the existing reporting-rate
  evidence helper. Missing approved rates refuse the run; no inversion, triangulation or
  current-rate substitution is introduced. Migration 0293 updates the report IPE description.
- Necessary validation passed: public dual-book GBP-to-USD report across April–September,
  revenue translated at 1.27 rather than September average 1.28/closing 1.29; nonzero ending
  balances translated at 1.29; driver tie-out, transaction/functional regression, six focused
  builder tests, catalogue migration parity and scoped lint/types.
- Remaining: granular framework/licence/advance-FX causal attribution, Book Bridge retained
  input replay, Adoption Bridge and Intercompany Pairs currency/source gaps, other documented
  incomplete adapters and final repository validation. OPEN reruns remain new evaluations;
  recorded rate evidence alone does not claim same-source report retention. No deployment.

## Book Bridge foreign-contract functional amounts — October 21, 2026

- The registered Book Bridge still rejected foreign contracts in Functional view. It now reads
  posted amount_functional revenue and the shared dated functional member-balance projection
  for each book. Transaction view retains original-currency values; no single current rate is
  applied to historical-layer liabilities or monetary balance targets.
- A foreign functional difference left in OTHER no longer presents advance-consideration FX
  as a proven zero: that driver is unquantified while the residual stays in OTHER and the driver
  tie-out still sums to the book difference. Existing collectibility, loss-provision and cost
  impairment precedence remains. Reporting currency is explicitly refused instead of being
  silently treated as functional. Migration 0292 describes the expanded currency basis.
- Necessary checks passed: both-book foreign revenue through public report runs (GBP 4,790.61
  transaction versus posted USD 6,131.98 functional), existing collectibility bridge and output
  checks, driver/tie-out behavior with an unclassified FX residual, catalogue parity and types/lint.
- Remaining financial Reporting work is explicit: Book Bridge reporting-currency translation,
  granular causal attribution of framework/licence/FX effects and same-source retention; inspect
  Adoption Bridge and Intercompany Pairs currency/source gaps next. These are real builder
  limitations, not closed by the preceding audit-report retention work. No deployment.

## Audit chain verification report retained inputs — October 21, 2026

- Historical chain-verification reports now require the original verification transaction to
  have committed by known_at, in addition to the existing finished-at range. Migration 0291
  queues commit evidence atomically, reuses the recovery worker and refuses fabricated history
  on nonempty upgrade or removal of retained commit evidence on downgrade.
- New reports retain the verification fields consumed by row generation, historical commit
  evidence and the applied date range. Same-source reruns rebuild collision-safe row keys,
  verification counts and failure counts without live verification reads. Workspace binding,
  existing report permission checks and digest-file references remain intact; unused failure
  payloads are not retained. Old OPEN runs remain labelled as new evaluations on rerun.
- Necessary checks passed: real overlapping verification commit, old/new populations and FAIL
  counts, equal-finish-time row keys, input-only rebuild, commit recovery, public rerun after a
  later failing verification, catalogue parity, database architecture and scoped lint/types.
- Approval-reference audit completed: the normal submission writer inserts a request and all
  routed steps in one transaction (`approvals/engine.py`); routing/automatic decisions consume
  published rule versions. DB-04 permits rule edits only while the parent is DRAFT/TESTED and
  prevents edits to used published/superseded definitions (`db/migration_ops.py`). The earlier
  first-step/rule-reference TODO does not require another history subsystem for these flows.
- Remaining: other OPEN report adapters and final repository validation. No deployment.

## Approval entity-code history and display semantics — October 21, 2026

- Historical Approvals Register now resolves entity codes from the latest source revision whose
  original transaction committed by known_at. A rename committed after cutoff cannot rewrite
  the old display. Missing entity-code history refuses explicitly; source revision IDs and
  commit timestamps are retained alongside the already retained approval inputs.
- Record-basis reads keep current codes, and existing retained reports rebuild from their
  original inputs. Migration 0290 synchronizes the catalogue description.
- Necessary verification covers an actual entity rename held across cutoff, old/new report
  codes, source revision evidence, retained rebuild, existing public register flow, catalogue
  parity and scoped lint/types.
- Scope correction from implementation evidence: personnel names are intentionally current
  identity labels, including anonymization (`domain/platform/actors.py`, `approval_queries.py`).
  Reconstructing erased/past names is not a missing feature. Approval step names/numbers are
  immutable after insertion (0013 permits only status/activation/completion updates); a separate
  name-change history is unnecessary. These findings supersede earlier broad display-history
  TODOs. Retained reports still preserve their consumed inputs under existing artifact controls.
- Remaining: confirm first-step availability and rule-reference validity at historical cutoffs,
  finish other OPEN report adapters and final repository validation. No deployment.

## Approval register retained display and decision inputs — October 21, 2026

- Approvals Register now retains the consumed requests and decisions, resolved personnel and
  entity labels, first-step names, automatic rule keys/versions and applied date range. Both
  initial builds and same-source reruns feed the same row/control calculation; reruns make no
  live approval or display-name reads. Decimal amounts, UUIDs and timestamps round-trip exactly.
- Retained inputs are bound to the workspace and complete report entity scope. Existing
  functional-view restriction, request population permissions and historical commit filtering
  remain in place. Old OPEN runs keep their source classification and reevaluate on rerun.
- Migration 0289 synchronizes catalogue metadata. Necessary checks cover multi-step/pending/
  automatic decisions, resolved names/rules, exact money, recomputed control totals without a
  database, scope isolation, public rerun after a later approval, catalogue parity and types/lint.
- Remaining: first-generation historical actor/entity/step/rule display resolution and other
  OPEN report adapters. Retention freezes the inputs actually consumed; it does not claim that
  current labels were historically correct on a report's first generation. No deployment.

## Audit export committed cutoff and retained inputs — October 21, 2026

- Historical Audit Log Export now filters original audit transaction commits by known_at for
  both the workspace and contract-trail paths. Business occurred_at range/filter semantics stay
  intact; record basis preserves transaction-local visibility.
- New exports retain redacted input events (including historical commit evidence) and rebuild
  rows, canonical JSON cells and chain control totals from those inputs. Same-source reruns do
  not query today's audit population. Retained evidence is workspace-bound. PostgreSQL IP
  address values are normalized to text before canonical serialization.
- The source contract is now retained_inputs. Old OPEN bindings remain explicitly OPEN and
  rerun as new evaluations rather than claiming reproduction. Migration 0288 synchronizes the
  catalogue. Existing exported rows/columns and saved files remain compatible.
- Necessary verification: overlapping original audit commits with both selectors, database-free
  retained rebuild and recomputed totals, redaction/workspace isolation, public rerun after a
  later audit event, legacy source labels, catalogue parity and scoped lint/types.
- Remaining: first-generation actor/display-name histories, approval-register rule/step display
  inputs and other OPEN report adapters, followed by final repository validation. This audit
  export is a selected event listing, not a complete audit-chain verification. No deployment.

## Contract sample approval and audit commit visibility — October 21, 2026

- Migration 0287 queues original audit-event commits atomically. A fixed audit source kind
  handles monthly partition triggers; an immutable occurred_at locator validates the original
  event in its partition. Existing recovery archives timestamps. Upgrade requires an empty
  audit table rather than fabricated history, and retained audit commits prevent downgrade.
- Sample approvals/audit v2 now applies one committed cutoff to request revisions, decisions
  and linked audit events. A late approval preserves the earlier request state and excludes
  both the later decision and its audit event. Decision/audit commit timestamps are retained;
  missing request history refuses explicitly. Original request comments remain in the snapshot.
- Current whole-population permissions, linked-contract checks, redaction and subject-hash
  verification remain enforced. Saved archives keep their original bytes and schema.
- Necessary checks passed: overlapping request/decision/audit transaction at old/new cutoffs,
  exclusion before request commit, commit recovery, immutable audit partition locator,
  full ZIP/PDF/XLSX sample flow, catalogue parity, database architecture and scoped lint/types.
  The full sample fixture advances its clock past real attachment commit before live capture.
- Remaining: standalone audit-export cutoff/retention, first-generation actor/display names,
  register rule/step display inputs and other OPEN report adapters. This completes the sample
  pack's approval/audit commit cutoff, not all historical source reconstruction. No deployment.

## Approvals register committed request state — October 21, 2026

- Migration 0286 captures source-owned approval-request revisions, including terminal state
  transitions. Original commit evidence uses existing revision recovery. Upgrade requires an
  empty request table instead of fabricated history; retained revisions prevent downgrade.
- Historical Approvals Register selects committed request revisions and original decision
  commits before applying status filters. Late submission stays outside the old population;
  late approval preserves the preceding PENDING state and earlier decisions. Default record
  basis retains its existing business-time behavior.
- Necessary checks passed: real overlapping approval/decision commits, PENDING versus APPROVED
  status filters at old/new cutoffs, exclusion before request creation commit, existing public
  register flow, catalogue parity, database architecture and scoped lint/types. No deployment.
- Remaining: register names/rule/step display inputs and same-source retention remain OPEN;
  audit commit visibility must be completed before switching sample approval packs to the new
  request reader, so this does not combine committed requests with an inconsistent audit slice.
  Personnel names and other listed report inputs still need work; no completion claim is made.

## Contract sample attachment lifecycle history — October 21, 2026

- Migration 0285 captures source-owned attachment revisions, including void transitions;
  original revision commits use the existing queue/recovery path. Upgrade requires an empty
  attachment table instead of fabricating history, and retained revisions prevent downgrade.
- Sample documents v2 chooses the latest committed attachment revision by request cutoff.
  Late-committed creation stays out; late-committed voiding preserves the original association
  at an earlier cutoff. Each index row retains its source revision and commit time. Referenced
  contract events also require their original commit before cutoff.
- Current subject/file authorization, availability, upload-purpose limits, safe archive paths,
  byte hashes and archive limits remain mandatory. Historical selection does not restore
  shredded bytes or bypass revoked file grants. Existing saved packs keep their original bytes.
- Necessary checks passed: real overlapping attachment creation and void transactions, original
  bytes and revision evidence, full sample archive/PDF/XLSX flow, catalogue parity, database
  architecture and scoped lint/types. The full sample fixture now commits attachments before
  collecting them, matching the historical visibility contract. No deployment.
- Remaining: actor/display-name history, approval-request/audit histories, and the other OPEN
  report inputs. File metadata still follows current authorized file-read semantics; unavailable
  historical bytes or incompatible metadata refuse rather than fetching external references.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps passed on clean 74bd148 (October 15): all 86 pinned Python runtime packages and npm runtime dependencies report zero advisories. Rerun on the final candidate.
- make docker-build passed on clean b4b8210 (October 15); rerun on the final candidate.
- make compose-verify passed on clean 74bd148 (October 15), including cleanup. Rerun on the final candidate.
- make zap-baseline passed on clean 4c4b583 (October 15), including cleanup; one documented low COEP warning and three informational alerts remain. Unauthenticated surface only; rerun on the final candidate.
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- make restore-drill passed on frozen d7e8715 (October 15), exercising backup and restore-verify
  on a fresh disposable server. Rerun on the final candidate; hosted recovery is outside this scope.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
