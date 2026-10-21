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

## Contract event and version commit visibility — October 21, 2026

- Original contract-event and computed-version transactions now have database-controlled
  commit evidence, queued atomically with each source and archived after ordinary writes.
  The minute worker also recovers pending source evidence in isolated keyset batches.
  Delegated SYSTEM activation units are covered by that durable recovery path; read-only
  queries can resolve the real timestamp before archival. Archived evidence is immutable.
- Shared historical version selection excludes late commits before choosing the latest
  candidate, retaining the preceding version correctly. RPO history and the touched history,
  book-bridge, prior-obligation, SSP/allocation, modification and estimate readers use the
  same cutoff protection. Explicitly bound original version identities remain compatible.
- New event/version extracts and BBR event inputs retain their actual commit timestamps.
  Incremental event/version exports use (known_since, known_at] in commit time, so backdated
  events and computations committed after a prior export are picked up in the next window.
  Published columns are unchanged; old bound extracts retain their original input basis.
- Migration 0277 adds tenant-isolated evidence, pending indexes and synchronized metadata
  for the affected report definitions. It requires empty contract-event/version tables,
  refusing existing history rather than fabricating timestamps. Sandbox evidence regenerates
  with its own copied/recomputed sources; no production transaction identity is reused.
- Verified a real append/recompute transaction committed after an independent cutoff: the
  prior version and RPO history remain selected, BBR excludes the late event, both next-window
  exports include the new data, and new/legacy bindings reproduce. Public event/version and
  three latest-version extracts, archive immutability, catalogue parity and snapshot inventory
  checks pass, with scoped lint/types. No deployment.
- B4-11 remains open for mutable journal/GL revisions, membership/configuration state and
  report-specific source readers not covered here (including full historical modification
  state). Commit evidence alone does not reconstruct prior values of mutable rows. The wider
  final-candidate verification list remains outstanding; independent accounting sign-off and
  migration-to-live work remain outside the owner's development scope.

## Retained ledger source and incremental export windows — October 21, 2026

- New subledger extracts and bookings/billings/revenue ledger contributions exclude postings
  committed after known_at, even when their insertion and business record times precede it.
  Original commit timestamps travel with retained input rows and are checked on rebuild.
- New incremental subledger extracts use (known_since, known_at] in actual commit time.
  A posting still uncommitted at the previous cutoff therefore appears in the next export,
  including backdated business records. Existing export columns remain unchanged; old bound
  extracts keep their recorded_at interpretation and original retained inputs.
- Migration 0276 synchronizes both report definitions with this interpretation. Database
  catalogue parity, a real late-commit/next-window journey, old/new bound extract rebuilds,
  the public JSON/CSV extract controls and rerun, and retained BBR cutoff validation pass.
  Six focused BBR unit cases plus scoped lint/types pass. No deployment.
- B4-11 is still open for non-ledger inputs such as contract events, version availability,
  journal state and other report-specific readers. This increment fixes the ledger source
  populations above; it does not claim full cross-source historical snapshot reconstruction.

## Automatic commit-evidence recovery — October 21, 2026

- The existing minute worker sweep now retries pending posting commit evidence per tenant.
  Recovery uses short batches, row locks with SKIP LOCKED, and savepoints per posting.
  Keyset progression passes failed entries so they cannot starve later pending rows; each
  failed entry is retried on the next sweep. Successful batches commit independently.
- Immediate after-commit retention remains the normal path. Migration 0275 adds a partial
  pending-only index so routine recovery does not scan the full ledger. Recovery logs posting
  failures and per-tenant retained/failed totals. Tenant recovery failures do not stop the
  existing job sweep or the next tenant.
- Verified against PostgreSQL: an injected statement failure on the first pending posting
  rolls back only that posting, the next batch retains the second, the next sweep recovers
  the first, and another sweep is a no-op. Minute-sweep tenant isolation and normal historical
  cutoff behavior pass; scoped lint and types pass. No deployment.
- This closes automatic retry of failed post-commit retention. PostgreSQL evidence already
  discarded before a worker can recover it remains unavailable and is explicitly refused;
  there is no invented fallback timestamp. Other B4-11 historical-source readers remain open.

## Historical ledger commit visibility — October 21, 2026

- Historical ledger readers now require the original PostgreSQL commit timestamp, closing
  the insertion-before-cutoff/commit-after-cutoff race. Commit evidence is queued with the
  seal and retained after commit. Database guards prevent caller-supplied timestamps and
  later changes; read-only historical queries can resolve pending evidence directly.
- Ten report definitions version this ledger interpretation. Older bound runs preserve
  their seal-time basis. Disaggregation catalogue metadata is also brought into agreement
  with its existing ledger and multi-currency implementation.
- PostgreSQL requires track_commit_timestamp=on before posting; Compose and the optional
  GCP configuration include it, and check_env --db checks it. Migration 0274 requires an
  empty posting-seal table and refuses populated ledgers rather than inventing old commits.
  This is a repository-development prerequisite, not a migration-to-live deliverable.
- Sandbox refresh regenerates commit evidence with its own derived postings. No production
  transaction IDs are copied into sandbox evidence. No sandbox lock requirement is added.
- Necessary verification covers concurrent late commits, immutable timestamps, pending
  evidence fallback/recovery, read-only access, historical/record basis and catalogue parity.
  Scoped lint/types and the affected configuration/catalogue/snapshot checks pass.
- Remaining B4-11 work: other historical sources and direct report-specific seal queries
  still need commit visibility. Post-commit hook failures leave recoverable pending rows;
  automatic retry/monitoring before PostgreSQL discards old transaction evidence remains
  to implement. Expired evidence is refused, never replaced with an estimated timestamp.
  This increment does not close all historical-source gaps. No deployment.

## Royalty lifecycle and supported public workflow — October 21, 2026

- Four original-engine Reporting journeys verify minimum-guarantee netting, downward
  statement corrections, licence satisfaction before/after the eligibility boundary and
  same-day statements before/after exit. All movement lines reconcile; the fixture now reads
  the actual recognition method instead of labelling every obligation USAGE.
- The public workflow intentionally rejects a batch mixing Step 1 reassessments with manual
  usage (API-R-30). Verified rejection leaves computation count unchanged. The supported
  separate-review sequence accepts usage while excluded, restores eligibility and preserves
  the earlier bound report on rerun. Both existing and usage-bearing public variants pass.
- A single public manual batch is therefore not a missing UI feature to enable by weakening
  controls. Ordered initial historical computations remain covered at the original-engine
  and report-builder boundary; no claim is made about every history-import route.
- This increment closes the stated royalty guarantee/statement/satisfaction witness and
  clarifies the public mixed-batch limitation without changing production logic. Scoped lint
  passes. Next implementation focus is B4-11 arbitrary historical commit visibility;
  final-candidate checks below remain outstanding. No deployment.

## Performance events in initial RPO eligibility batches — October 21, 2026

- Ordered initial Reporting timelines now admit delivery, actual return, billing and credit
  events with original before/after monetary evidence. Performance-driven net allocation
  changes are VC movements while included; changes while excluded enter with the remaining
  re-entry balance. Retained evidence also separates return-window expiry before a later event
  from that event's own cause, and measures expiry after the final event through report end.
- Migration 0273 versions this interpretation for RPO/rollforward. Older bound runs retain
  their original timeline. Missing required performance positions cannot silently fall back
  to a date-only timeline that drops those events.
- Thirty-four scoped original-engine/report cases pass, including twelve actual-return and
  delivery cases spanning pre/post-exit events, excess/partial expected returns, and expiry
  before/after the eligibility boundary. All reconcile with zero unexplained movement.
  Public sequential eligibility/re-entry and bound rerun pass; both catalogue definitions
  match upgrade/downgrade; scoped lint/types pass. No deployment.
- Remaining work includes public initial mixed-batch end-to-end coverage, full royalty
  eligibility lifecycle coverage and B4-11 arbitrary historical commit visibility. Billing
  and credit event admission is implemented but has no dedicated new mixed-batch witness in
  this increment. This is feature progress, not a repository-completion claim.

## Return-path original event positions — October 21, 2026

- Return estimate pins now carry their original applying-event order from stage 04.
  Recognition selects both the estimate and the allocation unit rate at the requested
  event position. Actual returns after an estimate consume its remaining expected units,
  including later returns on the same date; stage 04 pricing and stage 09 recognition
  now use the same ordering rule.
- RPO event-position evidence now includes return-path net fixed allocations using that
  same cutoff for the segment rate, expected units and actual returns. A later estimate
  or price change cannot rewrite an earlier eligibility exit. Legacy internal pins
  without event-order metadata remain excluded from positional evidence.
- Seventy-seven scoped pricing, returns, disclosure and ordered-eligibility cases pass,
  including original pricing-to-recognition same-day return consumption, frozen recognition
  across later estimate/price changes, and positional trace re-evaluation. Scoped lint/types
  pass. No schema/catalogue change; existing bound runs retain their original trace.
- Still open: initial Reporting timelines that include actual return/delivery causes,
  public mixed-batch end-to-end coverage, full royalty eligibility lifecycle coverage and
  B4-11 arbitrary historical commit visibility. This fixes positional return amounts; it
  does not claim every return lifecycle is enabled in the report. No deployment.

## Ordered initial-batch RPO attribution — October 21, 2026

- Reporting now consumes original event-position amounts for initial computations containing
  eligibility transitions and monetary events. It orders actual transitions, amendments,
  estimates and usage by original date/sequence/key, preserving one computation identity.
  Changes before exit are modification/VC movements; changes while excluded enter through
  the remaining re-entry balance. Multiple transitions on one date no longer require a
  date-end proxy. Revenue after re-entry uses its original event-position opening amount.
- Original position metadata is checked against immutable events. Required missing
  obligation positions refuse rather than use day-end amounts. Later retained computations
  load positional evidence for restated segment openings. Old traces retain supported older
  timeline behavior; old bound runs do not enable the new ordered-evidence feature.
- Migration 0272 records this interpretation for RPO and rollforward. Both catalogue
  definitions match migration upgrade/downgrade. Thirty scoped original-engine/report checks
  pass, including 12 same-day usage/estimate/amendment cases before/after exit, with/without
  re-entry. The public sequential collectibility/re-entry and bound rerun check passes;
  scoped lint/types pass. Changes publish directly to main; no deployment.
- Remaining: public initial mixed-batch end-to-end coverage, return-path positional
  rates/estimates (not substituted), full royalty eligibility lifecycle coverage, and B4-11
  arbitrary historical commit visibility. This increment does not claim repository completion.

## Original event-position amounts for RPO — October 21, 2026

- Stage 09 retains before/after fixed allocation, realized consideration and cumulative
  revenue at eligibility, amendment, estimate and usage events of collectibility histories.
  Each point carries the original event key, date, sequence and source role; its trace
  formula re-evaluates. The report reader rejects changed sources and incomplete triples.
- Realized royalties now measure the requested date/position independently of frozen
  recognition. A statement arriving after a same-day eligibility exit increases realized
  consideration without retrospectively increasing the frozen revenue target.
- The 34 scoped usage, royalty, eligibility and original-position checks pass; scoped
  lint/types pass. No schema or report catalogue change in this increment.
- Reporting does not yet consume these positions: enabling ordered initial-batch attribution
  and its bound-run compatibility remains next. Return-path positional allocations are
  intentionally absent until their rates/estimates support the same event cutoff; readers
  must not substitute date-end amounts. Public mixed-batch and full royalty lifecycle
  witnesses, plus B4-11 historical commit visibility, remain open. No deployment.

## Ordered Step 1 recognition freezes — October 21, 2026

- The engine now preserves each actual Step 1 transition's original event order in its
  internal contract state, alongside the existing date history. Recognition at an event
  position observes only preceding status transitions. Once eligibility is lost, fixed,
  usage and royalty recognition freeze immediately before that status event, excluding
  later changes even when they share its date.
- Same-day post-exit estimates retain a zero catch-up with explicit frozen evidence; a later
  same-day criteria re-entry cannot retrospectively change that earlier estimate position.
  The newer allocation remains available when recognition resumes. Date-only legacy
  internal states preserve their earlier behavior. Book memo rebinding and original-cut
  manual projection snapshots retain/filter the corresponding ordered history.
- Four original-engine witnesses distinguish pre/post-exit usage, amendments and estimates
  and a later same-day re-entry. The 91 scoped recognition, eligibility, estimate and book
  checks pass, including existing memo reuse. Scoped lint/types pass. Public sequential
  eligibility/rerun regression also passes.
- This fixes the engine's frozen recognition semantics; Reporting still needs original
  event-position monetary evidence before enabling the currently refused same-day batches.
  Public mixed-batch and full royalty eligibility witnesses and B4-11 historical commit
  visibility remain open. No deployment, schema or expanded approval requirement.

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
