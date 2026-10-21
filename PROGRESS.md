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

## Committed contract identities in sample evidence — October 21, 2026

- Sample selection v2 and computation member files now resolve contract identity fields from
  committed header revisions at the requested cutoff, retaining revision identity and commit
  time. Current selectors still authorize the requested contracts; historical/current owner
  scopes are checked before export. Missing cutoff history refuses explicitly.
- Contract external IDs remain fixed by the existing application rule; no rename capability
  was added. The gap closed here is committed existence and header-version provenance, not a
  new mutable business identifier. A backdated creation committed after cutoff cannot be
  presented as an already-existing sampled contract.
- Migration 0284 synchronizes catalogue metadata. Necessary checks passed: real overlapping
  header/event/version changes, consistent selected/member revision identities, refusal before
  the first committed header, full sample archive/PDF/XLSX flow, catalogue parity and scoped
  lint/types. Existing stored archives remain unchanged. No deployment.
- Remaining: actor/display-name history, approval-request/audit and document histories, and
  other report-specific inputs still listed as OPEN. These contract identities do not replace
  the remaining source-specific cutoff work or final repository release verification.

## Contract sample event and version commits — October 21, 2026

- Event sample files v2 filter original event commits by known_at and retain the timestamp
  alongside original/redacted payload digests. Effective-date scope and provenance checks stay
  intact; an event recorded before cutoff but committed later is excluded from that sample.
- Computations index v2 and version evidence retain original version commits. Filtering happens
  before ranking selected versions, keeping the preceding committed version when a newer
  calculation commits late. Full allocation, trace and future planned schedule evidence remains.
- Migration 0283 updates the sample catalogue description. Existing archives remain original
  bytes. The pending-source check now includes approval decisions added by 0282 and verifies
  recovery of all pending kinds, rather than assuming only event/version/revision sources.
- Necessary checks passed: actual overlapping event+computation transaction with old/new sample
  reads and selected versions, complete sample archive/PDF/XLSX flow, commit/redaction validation,
  worker recovery, catalogue parity and scoped lint/types. No deployment.
- Remaining: actor/display-name history, sample contract identity labels, approval-request/audit
  and document histories. These readers now cover immutable event/version commit availability;
  this does not claim complete historical reconstruction of every source in a sample pack.

## JE Population approval and acknowledgement commits — October 21, 2026

- Migration 0282 queues original approval-decision and posting-acknowledgement commits
  atomically with insertion. The existing tenant recovery worker archives pending commit
  evidence. Upgrade requires empty decision/ack tables rather than inventing historical
  timestamps; downgrade refuses retained evidence. Catalogue metadata is synchronized.
- First-generation historical JE Population filters these ancillary records by actual commit
  before choosing its approver and GL document. A backdated but late-committed record cannot
  enter the old cutoff. Record-basis and close-owned reads retain transaction-local behavior;
  previously retained reports continue to rebuild from their saved inputs.
- Necessary checks passed: real overlapping decision/ack commits with old/new cutoffs,
  preceding approver retention, recovery timestamp archival, public JE Population reruns,
  existing close/reopen population flow, catalogue parity and database architecture; scoped
  lint/types pass. No deployment.
- Remaining: first-generation actor/display-name history and broader sample approval-request,
  audit, event, computation and document histories. This change covers JE Population's
  decision/ack readers; it does not silently apply a partial cutoff to entire approval packs.

## Contract sample journal commit evidence — October 21, 2026

- New sample/journals.json v2 excludes journal lines committed after the request cutoff and
  resolves run/batch lifecycle through committed revisions. Cancelled lines remain in evidence
  with their state at cutoff; a late-committed cancellation cannot rewrite the old state.
- Posting-entity discovery respects complete original posting commits. Every drilled source
  line must have committed by cutoff before contributing to whole-line reconciliation and the
  separately calculated sampled-contract amount. Evidence includes original journal/posting
  commit times and run/batch revision identities; existing archived packs remain unchanged.
- Migration 0281 synchronizes the contract sample catalogue's source tables and cutoff basis.
  Necessary checks passed: exclusion before journal commit, actual overlapping cancellation,
  historical/latest state labels, contribution conservation, full computation/sample archive
  and PDF/XLSX flow, catalogue parity, scoped lint/types.
- Remaining: first-generation ancillary approval/ack/name histories and broader sample event,
  computation, decision and document histories need their own cutoff review. Period dates
  changed after cutoff continue to refuse explicitly. This completes the journal slice, not
  an assertion that every source in the entire evidence pack has historical commit coverage.
  No deployment.

## JE Population retained inputs — October 21, 2026

- New JE Population reports retain source records, resolved actor/display labels and independent
  run debit totals. Same-source reruns reconstruct rows, currency controls and the run-total
  tie-out through the normal builder without querying live sources; entity/book scope remains
  enforced. This replaces the report's OPEN adapter with retained inputs.
- Historical populations use original line commits and committed run/batch revisions, including
  include-cancelled selection. A late-committed cancellation leaves the old cutoff unchanged.
  Record-basis and close-owned DATASET_FREEZE reads retain transaction-local journal visibility.
- Old OPEN records remain explicitly OPEN and rerun as new evaluations even after adapter
  promotion; they are not mistaken for records with complete retained evidence. Migration 0280
  synchronizes the report's source/retention description with the catalogue.
- Necessary checks passed: public historical/current/include-cancelled flows, exact rerun after
  entity rename and cancellation, old OPEN rerun, existing close/reopen population and controls,
  retained reconstruction without a live session, scope refusal, independent tie-out input,
  catalogue parity, focused source-binding/export units and scoped lint/types.
- Remaining historical-source gaps include first-generation approval/ack/name inputs and sample
  journal evidence. Retention guarantees repeatability of consumed inputs; it does not assert
  arbitrary historical reconstruction of these ancillary sources. No deployment.

## Committed journal lifecycle and line availability — October 21, 2026

- Migration 0279 captures immutable journal-run/batch revisions and original journal-line
  transaction evidence. Ordinary generation archives line commits after commit; the existing
  recovery worker also covers pending evidence. No invented history: upgrade requires empty
  journal tables, and retained new evidence prevents downgrade.
- Journal exports resolve lifecycle revisions by actual commit cutoff, so a cancellation
  inserted before cutoff but committed afterward cannot remove lines from the old report.
  Incremental exports use line commits in (known_since, known_at]; public columns stay fixed
  and older retained bindings preserve their original interpretation.
- Historical revenue waterfall/disaggregation journal comparisons use committed line
  populations and run state. BBR journal comparison inherits the export behavior. Production
  actuals captures consume resolved committed states without reinterpreting application clocks.
- Necessary checks passed: public JSON/CSV exports and retained reruns, real overlapping
  cancellation commits, incremental lines, historical/current journal totals, archive guards,
  catalogue parity, database architecture, focused actuals/catalogue/BBR units, lint/types.
- Remaining: JE Population complete retained inputs, sample journal evidence and other mutable
  report inputs/configuration still need work. This does not claim all historical sources are
  complete. No deployment or actual-business migration is required or performed.

## Committed GL and contract-source revisions — October 21, 2026

- Migration 0278 extends original transaction evidence to immutable report-source revisions
  (GL reconciliation state, contract headers and customer/entity code labels). Source triggers
  queue evidence atomically; the existing minute recovery archives it. Existing revision
  history is not assigned invented commits: upgrade requires an empty revision table, and
  retained revision-commit evidence prevents downgrade.
- GL bridge v7 filters revision commits before ranking source identity and review state in
  its single snapshot query. A change inserted before a report cutoff but committed afterward
  no longer replaces the original reviewed/reopened state on a later historical read.
  Revision identity, insertion time and actual commit time are retained. Bound v1-v6
  comparisons keep their original evidence and control rules.
- Contract exports resolve header and code-label revisions at committed cutoffs. New
  incremental exports return the latest contract when its header or customer/entity code
  changed in (known_since, known_at], covering updates and late commits as well as new rows.
  This remains an upsert dataset, not a deletion feed. Columns are unchanged; old bound
  extracts preserve their original creation-time interpretation and retained labels.
- Necessary checks pass: public reviewed GL/reopen flow with a real overlapping commit and
  subsequent historical replay, old-v6 GL binding, source-owned contract revisions, late
  header updates, code-only incremental changes, new/legacy extract bindings, archive guards
  and catalogue parity. Scoped lint/types pass. No deployment.
- Remaining historical work includes journal-run state and other mutable memberships,
  configuration and report-specific inputs. These changes cover retained GL and contract
  revisions; they do not claim arbitrary reconstruction for every mutable source.

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
