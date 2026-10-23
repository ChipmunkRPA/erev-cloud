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

## Legacy journal summary retained reconstruction — October 22, 2026

- New GROSS/DELTA summary runs retain original per-book aggregates, resolved entity/account/key
  labels, window and source line/partition/posting references. Shared pure view calculation
  rebuilds line nets, debit/credit sides, entity balances and currency totals. Bound reruns
  validate tenant/entity scope and mode/book/date selection without current ledger reads.
- DELTA keeps the existing primary-plus-LEGACY convention. Current book-enable validation applies
  to original runs; reconstruction uses their retained inputs. Source membership includes original
  subledger line IDs. Older explicit OPEN bindings keep their original semantics. Migration 0322
  freezes the report IPE; this does not change journal posting or add financial-currency views.
- Necessary verification passed: 18 focused reconstruction/source-binding cases, including
  USD/EUR, same key across entities and sign changes that recalculate debit/credit totals.
  Actual GROSS and DELTA API/worker runs reproduce rows and output hashes. Scoped lint/types and
  migration metadata parity passed. No deployment; final repository verification remains open.

## Legacy contract exports retained reconstruction — October 22, 2026

- Both legacy contract history and latest-contract exports now retain current/predecessor
  obligation-version inputs, original labels and the verified exact trace texts used by the
  71-column format. Shared reconstruction restores source dates/timestamps and reruns the legacy
  column calculations without reading current contracts or trace storage.
- Tenant/entity scope, report identity and date/book/contract selection are checked. Current and
  predecessor obligation IDs are retained as source membership. Exact-text refusals still apply
  when the original run reads its trace; unavailable activity remains explicitly unavailable.
  Older OPEN runs keep their original behavior. Migration 0321 freezes both IPE definitions.
- Necessary verification passed: 32 focused exact-export/source-binding cases, including
  database-free reconstruction, scope refusals and recalculated remaining SSP. Actual API/worker
  runs of both 71-column exports and latest-status reproduce original rows/output hashes; scoped
  lint/types and both metadata checks passed. No deployment. Legacy JE summary, other documented
  gaps and final repository verification remain outside this completed batch.

## Latest contract status retained reconstruction — October 22, 2026

- New latest-status runs retain selected contract-version inputs, original contract/product/entity
  labels, resolved as-of obligation cuts and member/entity balance cuts. Bound reruns validate
  tenant/entity scope and book/as-of/contract selection, then recalculate reported allocation,
  remaining allocation and deduplicated balance totals without live contract reads.
- This is reconstruction from retained resolved cuts, not a new engine computation. The live
  as-of calculation, transaction-currency presentation and legacy export behavior are unchanged.
  Older OPEN runs retain their original live-evaluation behavior. Migration 0320 updates IPE.
- Necessary verification passed: 17 focused source-binding/reconstruction cases and the actual
  16-obligation latest-status API/worker workflow, including identical rerun rows/output hash;
  scoped lint/types and frozen metadata parity. No deployment; remaining documented work and
  final repository verification are not claimed complete.

## SoD conflict retained reconstruction — October 22, 2026

- New runs retain the original scoped conflict population, rule functions, held role permissions,
  delegation permissions/names/end dates and candidate exception approval/revocation/validity
  inputs. Same-source reruns validate tenant/entity scope and as-of selection, recalculate
  conflict predicates and exception coverage, and rebuild rows/totals without live access reads.
- Necessary verification passed: 61 focused access/source-binding cases plus the actual report
  API/worker exception-revocation flow. Fresh reports show an uncovered conflict; saved covered
  and empty runs reproduce identical rows/output hashes. Scoped lint/types and migration 0319
  catalogue parity passed. Original historical-cutoff limits and older OPEN-run behavior remain.
- This preserves selected report inputs; it does not add role-permission history or expand
  approvals. Saved-run access still uses current authorization. No deployment.

## User access retained reconstruction — October 22, 2026

- New runs retain member names/status, role/entity grants, MFA state, last login, grantor,
  revocation timestamps and SoD exception references with the resolved as-of instant. Bound
  reruns validate tenant/entity scope and selection, restore typed members/grants and rebuild
  rows and membership/assignment totals without current identity or access-state reads.
- Necessary verification passed: all 60 focused access/source-binding cases and actual membership
  removal/report API and worker workflow. Fresh reports omit the removed member; the saved report
  reconstructs original grants and identical rows/output hash. Scoped lint/types and migration
  0318 IPE parity passed. Existing ad-hoc historical limitations remain; older OPEN runs keep
  their original behavior. Reading saved runs still requires current report authorization.
- Resolved the three previously recorded stale permission tests: expected inventory now includes
  both composite evidence packs and their audit/contract/export requirements; visibility checks
  distinguish the run-permission split from additional evidence-pack SQL predicates. The entire
  focused access test file now passes. No production permission policy was changed.
  No deployment; other documented Reporting/repository gaps remain.

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
