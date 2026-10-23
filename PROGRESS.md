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

## Confirmed royalty lifecycle gap — October 22, 2026

- Reproduced a native calculation failure for a delivered licence whose royalty is corrected
  downward after collectibility exit, with no re-entry. Allocation becomes 1,400 while frozen
  revenue stays 1,600; S09-INV-03 rejects the -200 remainder. Three neighboring no-reentry
  combinations compute and reconcile. This is a confirmed gap, not a completed feature.
- Requested the owner's revenue-treatment choice; no choice inferred and no calculation
  semantics changed. Exact conditions and the separate POL-199 awaiting-satisfaction gap are
  recorded in [ROYALTY-EXIT-CORRECTION.md](docs/release/ROYALTY-EXIT-CORRECTION.md).

## GL detail uploads — October 22, 2026

- The reconciliation file workflow now accepts an optional explicit BALANCE/DOCUMENT format
  in CSV/XLSX. Closing balances and period document amounts remain separate; documents are
  passed into the same comparison as connector data to identify direct GL entries, known
  eRev journals and ERP billing references. Legacy account/currency/amount files still work.
- Both request and worker validate functional currency, precision, document reference,
  posting date within the reconciliation period and a corresponding balance row. No document
  amount is added to the closing balance. Existing file access and source-retention controls apply.
- Added a downloadable header template and instructions in the attachment UI and user guide.
  Necessary checks passed: 33 parser/comparison cases, a populated API/worker comparison showing
  identical connector/file totals and difference items, and the focused upload UI case.
  Scoped lint/types passed. No database/API-schema changes and no deployment.
- This closes the file-upload document-attribution gap. It does not establish that every
  remaining Reporting/system gap is complete; foreign actual posted event attribution remains open.

## Optional modification currency equivalents — October 22, 2026

- Added an explicit Currency amount basis choice to the modification report. The default
  source basis is unchanged; spot_equivalent enables foreign Functional/Reporting views.
  Original TP/catch-up values remain alongside labelled analytical functional equivalents,
  with optional reporting equivalents and the pinned spot rate/reference.
- Functional conversion uses approved direct spot rates on/before the effective date under
  the report cutoff; reporting then uses that effective period's approved average. Each stage
  rounds to the destination minor unit. Unknown values remain empty and missing rates refuse.
  Same-source inputs retain the basis and rates, and reject switching basis on a bound rerun.
- Necessary validation passed: 29 focused backend cases, populated original-register and
  approved-rate integration cases, and seven parameter-toolbar cases. The rate integration
  uses supplied register sources with real rate publication/read paths; it proves draft-rate
  exclusion and future-effective-rate exclusion, not a new foreign native booking workflow.
  Scoped types/lint passed. No deployment.
- Actual functional per-event posted catch-up attribution remains outstanding. This feature
  offers explicitly labelled analytical equivalents and does not substitute for that work.

## Modification price composition — October 22, 2026

- New modification-register runs expose original-currency TP contributions: fixed consideration,
  constrained VC, returns, consideration payable, financing, noncash and posting rounding.
  Native traces retain before/after component amounts and original event references; the reader
  verifies complete composition and reconciliation to the event TP change.
- Totals count each modification once across obligation rows. Unknown historical composition
  stays empty. Retained runs without the new feature flag keep their original column shape.
- Necessary validation: 29 report/catalogue cases, 15 engine boundary cases and both populated
  modification report scenarios passed; K02 verifies the served fixed contribution of 60,000.
  Scoped lint/types passed. Foreign functional per-event allocation remains open. No deployment.

## Per-event modification amounts — October 22, 2026

- Native calculations now retain transaction price before/after each successful modification
  boundary, alongside existing obligation catch-ups. The modification register reads these
  event-specific amounts instead of conflating the whole application-version delta.
- Multiple modifications in one computation can be reported separately. Retained inputs include
  the verified trace hash and selected node identities; historical traces keep the guarded
  predecessor fallback and explicit shared-catch-up limitation.
- Necessary checks passed: 15 engine cases, 28 focused report/catalogue cases and two populated
  database report cases. A native two-event calculation yields TP changes +20,000/-10,000 and
  catch-ups +10,000/-5,000. Scoped lint/types passed.
- Foreign functional per-event allocation remains outstanding; this change enables original
  transaction-currency attribution, not an unsupported FX allocation. No deployment.

## Modification transaction-price predecessor evidence — October 22, 2026

- Applied modification TP change now requires the exact referenced predecessor in the same
  combination group, book and transaction currency, with an admissible known/commit cutoff.
  Missing predecessors no longer silently become zero and turn the whole contract price into
  a modification delta. Only an application with no previous-version reference starts at zero.
- New runs retain predecessor identities and price/scope evidence alongside their application
  version evidence. Previously retained report inputs preserve their original interpretation.
- Necessary verification passed: 19 focused register cases including missing/wrong-scope/future
  predecessors, negative delta and genuine first version; the populated K02 report still yields
  USD 60,000 TP change in transaction and reporting views. Scoped lint/types passed.
- This repairs the transaction-price provenance chain. Foreign functional per-event attribution
  remains incomplete; no unsupported currency view has been enabled. No deployment.

## Latest-production sandbox refresh — October 22, 2026

- Added LATEST to the existing reset command and the Sandbox copies reset dialog. The worker
  captures a new production seed at execution time, loads an editable successor, archives the
  old sandbox only after successful loading, and moves the requester's sessions. The new seed
  becomes the successor's future snapshot-reset baseline. Existing SNAPSHOT/EMPTY modes remain.
- Current all-entity tenant.snapshot access in the production source is required both when
  requesting and executing refresh, in addition to existing sandbox.reset and fresh MFA. The
  source and requester must be active. A sandbox grant alone cannot read fresh production data.
- Source writes are snapshot files/metadata and provenance; production business rows and existing
  files remain unchanged. Export failure marks the new source snapshot FAILED and leaves the old
  sandbox active; access revoked before execution refuses without creating the successor.
- Necessary verification passed: three populated API/worker cases (new post-seed source data,
  revoked source access, injected storage outage), two frontend reset/refresh cases, scoped
  lint/types. OpenAPI and generated frontend types include LATEST. No deployment.
- This completes the fresh-production refresh entry point identified in the previous checkpoint.
  Foreign modification currency attribution and final release-candidate verification remain open.

## Editable sandbox periods after copy/reset — October 22, 2026

- Implemented the owner's sandbox scope in the shared snapshot loader: periods previously opened
  in production stay open in a new sandbox; future periods stay future. Production close/lock
  transitions are no longer replayed. Copy, restore and snapshot reset use the same behavior.
- Load report v2 and sandbox audit evidence name OPEN_FOR_EXPERIMENTATION. UI copy and the user
  guide explain that production locks are not copied. Old sandboxes retain their existing state
  until replaced; historical blocked-load guards remain for those old records. Matching monetary
  state does not claim equal posting-period history, as the late-event case demonstrates.
- Replaced obsolete lock-chain acceptance with editable-copy acceptance and source-period
  immutability. Necessary checks cover populated copy, open-period computation, late events,
  load evidence, source close-gate independence and populated reset. Updated old test evidence
  inventories for existing computation/audit commit records, retaining source business-row checks.
- This does not add a one-click refresh from the latest production state: the current reset UI
  still offers its original seed or empty. That owner-requested workflow remains to be completed.
  Reporting foreign modification attribution and final candidate verification also remain open.

## Multi-currency tie-out display completeness — October 22, 2026

- The report viewer now displays the union of currencies in expected, actual and difference
  evidence. A currency appearing only in actual or difference is no longer silently hidden.
  Missing balances display the standard unavailable marker; the browser does not invent zeros
  or recompute monetary differences. Existing FAIL-only difference presentation is preserved.
- Necessary verification: all four targeted viewer tie-out cases passed, including actual-only
  and difference-only currency coverage. No deployment; remaining report attribution work stays open.

## Functional activity recognition provenance — October 22, 2026

- Native S13 revenue control flows now carry their upstream recognition source node into S12
  functional activity evidence. The report reader returns that link and requires its presence
  in the original trace and matching transaction currency when supplied. Earlier activity
  evidence without this optional link remains readable without inventing event provenance.
- The link identifies the original recognition producer, not necessarily the whole control
  relief amount: concessions, agent relief and calendar projection can adjust the target. It
  therefore does not imply unique modification-event allocation or enable unsupported foreign
  modification currency views by itself.
- Necessary verification passed: 7 focused native/reader cases, including full CHK-080 engine
  computation through report reading and missing-source refusal, plus all 13 FX-layer cases.
  Scoped lint/types passed. Existing posting amounts and flow ordering are unchanged.
- Asked the owner whether the foreign modification view should require actual attributable
  amounts or show clearly labelled currency equivalents. Pending a response, preserve actual
  evidence and do not allocate period totals to a single event without proof. Other engineering
  can continue. No deployment; overall development remains incomplete.

## Verified functional revenue activity reader — October 22, 2026

- Added a report-layer reader for the new S12 activity evidence. It replays the trace, validates
  obligation/entity/currency identities, checks every signed functional piece with multiplicity,
  and reconciles both transaction and functional movement sums against current-minus-prior
  cumulative revenue. It returns original dated signed flows with source references.
- Missing older activity, altered transaction counters, inconsistent formula results and currency
  mismatches fail explicitly. A matching net alone is insufficient: the source-piece population
  must also match. Period-aggregated flows are not assumed to be individual modification events.
- Necessary verification passed: the new reader checks on actual S12 historical-layer and negative
  revenue traces plus all 13 FX-layer cases (15 total); scoped lint/types passed. The historical
  USD 170 movement and subsequent USD -26 delta are reconstructed from their actual sources.
- This is a reusable report reading layer, not yet a served foreign modification currency view.
  Event-to-flow attribution and transaction-price currency presentation remain required before
  changing that report's admission. No deployment or overall completion claim.

## Functional revenue activity evidence — October 22, 2026

- Stage 12 now emits a revenue_activity_functional disclosure node for each positive/negative
  revenue control flow. Its signed functional amount is the sum of the actual historical-layer
  consumption or asset/credit pieces used by the existing cumulative target, with replayable
  signed inputs, transaction amount/currency, entity, obligation, source key and effective date.
- This adds no posting target and leaves existing cumulative amounts unchanged. It supplies
  flow-level evidence, which can be period-aggregated by the current S13 producer; it does not
  yet allocate functional revenue to individual modification events. Foreign-contract
  modification TP/catch-up reporting therefore remains incomplete and still refuses unsupported
  currency views. Reporting integration and event attribution are the next required steps.
- Necessary verification passed: 13 FX-layer cases with node-by-node formula replay and 10 native
  functional-member/cross-entity cases. The new case proves EUR 150 uses historical USD 170,
  rather than current-spot USD 210, and EUR -20 uses actual USD -26 credit pieces; cumulative
  targets remain USD 170/144. Scoped lint/types passed. No deployment or release-complete claim.

## Prior-period attribution reference population — October 22, 2026

- New prior-period revenue reports retain the original entity/period-to-contract-version
  reference population, including empty selections. Bound runs use those references before
  selecting their original versions and replaying trace attribution/identity checks, rather than
  rediscovering current revenue-line references. Book and period/entity scope must match.
- Modern bindings missing reference evidence fail explicitly. Older bindings that declared their
  reference population live retain that qualified behavior. Migration 0324 documents the source
  contract. Migration reconciliation is now the only wholly OPEN report strategy and remains
  outside the owner-authorized migration-to-live completion scope; this is not a claim that
  every Reporting business gap is closed.
- Necessary verification passed: 44 focused prior-period/source-binding cases including native
  attribution traces, later reference additions, scope mismatch and old/new binding behavior;
  actual K01 API/worker empty-report rerun with matching rows/hash. Scoped lint/types and frozen
  metadata parity passed. Foreign-contract modification functional TP/catch-up evidence remains
  a separate unresolved business gap; no ordinary FX conversion has replaced those amounts.
  No deployment; final repository verification remains open.

## AI call export retained reconstruction — October 22, 2026

- New call-log exports retain only the disclosed AIModelLogOut evidence and original requester
  scope. Rebuilds reauthorize the original actor before accessing retained content, refuse scope
  or identity substitution, and recalculate known/unknown usage totals. Promotion to administrator
  cannot widen an original OWN export. Original call IDs are captured as membership.
- Original reads still use current authorized visibility; callers cannot supply entity, actor,
  scope or historical filters. Retention adds no prompt/response body fields. Older explicit
  OPEN bindings keep their prior live-evaluation semantics. Migration 0323 updates description/IPE.
- Necessary verification passed: 24 focused catalogue/source-binding cases and database export
  visibility/CSV/XLSX safeguards, including new-log insertion, no-live-read reconstruction,
  promotion, revocation and actor/scope substitution. Scoped types/lint and metadata parity passed.
- Fixed a pre-existing current-catalogue seed helper failure reproduced against committed main:
  valid JSON regex/text escapes are now preserved, with JSON round-trip coverage. The historical
  migration seed remains byte-for-byte frozen. No deployment; final release verification remains.

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
