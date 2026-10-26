# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Feature development first; necessary checks; publish directly to main; no deployment.**

## Current owner-authorized goal — October 22, 2026

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

## Retained split causal reporting — October 24, 2026

Fixed-service ACTIVE transfers now have workbench/API entry, paired preview/approval and causal
reporting. Both ACTIVE contracts must use functional currency; specialist scenarios remain gated. See [checkpoint](docs/release/REGROUP-BOUNDARY-BASIS-2026-10-24.md).

## Rated usage entry — October 24, 2026

Usage/royalty/redemption entry supports approval; omitted member royalties refuse.
See [checkpoint](docs/release/USAGE-WORKBENCH-2026-10-24.md).

## Multi-currency disclosure packs — October 24, 2026

Three-currency packs retain original sources: [locks](docs/release/LOCKED-DISCLOSURE-CURRENCIES-2026-10-24.md).
Cost rollforward now admits aligned calendar records: [costs](docs/release/COST-CALENDAR-ALIGNMENT-2026-10-24.md).

## Combined actual hours and termination — October 23, 2026

Explicit scopes, complete member inputs and original-source reconciliation pass public approval
and report replay. See [hours](docs/release/COMBINED-ACTUAL-HOURS-2026-10-23.md) and
[termination](docs/release/COMBINED-TERMINATION-2026-10-23.md). Partial removal remains open.

## Agent and cross-entity POB sources — October 23, 2026

Agent contract/POB FIFO retains selected-group source owners, original POB caps and a single
combination total across three currency views. See [group sources](docs/release/AGENT-POB-GROUP-SOURCES-2026-10-23.md).
[Mixed sources](docs/release/AGENT-MIXED-SOURCES-2026-10-23.md) retain net totals and full sources,
with unavailable opening amounts explicitly marked. Cross-entity principal POB verifies original
[due-to sources](docs/release/INTERCOMPANY-POB-OPENING-2026-10-23.md).
Historical agent owners now use verified original membership: [checkpoint](docs/release/AGENT-HISTORICAL-OWNERS-2026-10-24.md).
Principal historical owners now use original membership proof in FIFO, reversals and due-to attribution.
Cross-performer contracting revenue (different calendars): [sources](docs/release/CONTRACTING-AGENT-SOURCES-2026-10-24.md).
Performing-entity agent revenue and specialist regrouping remain open.

## Acquired POB sources — October 23, 2026

Native acquisition evidence and public close/lock coverage are tracked in the
[acquisition checkpoint](docs/release/ACQUIRED-CLOSED-CUTOVER-2026-10-23.md).
Recomputed POB targets, closed-cutover sources/asset classification, public reports and locks now work in same functional currency;
mixed/agent/foreign-recompute paths remain unfinished.

## Rollforward Other explanation — October 23, 2026

- Read and retain the configured Other/closing threshold. Report and contract checks stay
  currency-specific; signed offsets and zero-closing exceptions remain visible. The viewer
  shows amounts and reconciliation links. Existing failed tie-outs are not waived.
- Saved reruns reuse the original threshold; older reports retain their original shape.
- Two backend unit cases, one populated rollforward database case and two viewer cases pass;
  scoped lint and types pass. No posting changes or deployment.

## Late billing reconciliation — October 23, 2026

- Post-lock invoices now reconcile in the first later period open at receipt on both sides;
  differences show the origin period and sign-offs retain it. Reviewed populations detect new
  late entries. Existing certified origin periods remain unchanged.
- Four populated billing workflows, five focused unit cases and two UI cases pass across
  targeted runs; scoped lint/types pass. See LATE-BILLING-RECONCILIATION-2026-10-23.md.
- Earlier modification-drill checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.



## Revenue-source compatibility and zero-share reversals — October 22, 2026

- Reporting now accepts native cumulative revenue's transaction-currency evidence, verifies
  its currency/precision and signed source total at each cumulative node, and retains the
  existing functional-currency check. The previous reader rejected these new native fields.
- Explicit zero-weight agent roles now produce a verified empty current source population,
  allowing prior attributed amounts to reverse even when gross sources span multiple layers.
  A rounded/net zero with nonzero weight still requires original attribution; no proportional
  source split is inferred. Original source identities remain retained.
- Necessary verification: focused reader/native-engine scenarios and public agent-report
  compatibility; see the source-class release note for results. No deployment.
- Superseded by owner-selected aggregate source sets and sequential modification causal analysis.

## Royalty RPO exemption for pending performance — October 22, 2026

- Replaced POL-199's unconditional zero cap with realized royalty still awaiting recognition.
  Native calculation retains dated remainder evidence; fixed minimum guarantees remain in
  RPO. RPO disclosure, rollforward and close-variance projection now read the same basis.
- Royalty and targeted-VC partial exemptions apply in policy order, are listed separately,
  and cannot exceed the remainder. Currency-projected rule amounts reconcile to the translated
  excluded total. New RPO bindings retain the feature flag; older bound runs keep their prior cap.
- Necessary verification passed: focused engine/report scenarios and the existing targeted-VC
  suite, combined partial-exemption currency rounding, and both public royalty workflows
  (pending/delivered) including original-evidence reruns. Example: 15,000 royalties less a
  12,000 guarantee produces a 3,000 exemption before satisfaction and no royalty remainder
  afterward. Scoped types/lint and frozen metadata parity pass. No deployment.
- Missing dated royalty evidence requires recomputation; no inferred quota is substituted.
  Post-exit correction is implemented below; event reporting uses owner-selected causal analysis.

## Owner-selected revenue completion — October 22, 2026

- BBR income cells retain net totals and complete original source sets, with no invented layer
  amounts; saved reruns and entity access controls preserve the evidence. Migration 0336.
- Royalty historical corrections can reduce income during exit (1,600 → 1,400); new income
  and upward rebounds remain blocked until re-entry. Native traces and RPO reconcile.
- Two populated agent/report workflows, 39 royalty/RPO cases, 50 trace/BBR cases and eight
  catalogue cases pass; scoped lint/types and populated metadata parity pass. No deployment.
- See CURRENT-DEVELOPMENT-SCOPE and ROYALTY-EXIT-CORRECTION for scope and verification.

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

Native boundaries retain transaction-price changes and catch-ups per event. Sequential causal
analysis now supplies the owner-selected functional/reporting interpretation; it is not a
per-event allocation of original journals. Retained evidence and historical limits are recorded
in CURRENT-DEVELOPMENT-SCOPE.md and the dated Reporting checkpoints. No deployment.

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
- Latest-production refresh is complete (LATEST reset); see the October 22 checkpoint in
  LIMITS-1.0.md. Modification attribution uses the implemented sequential causal analysis.
  Final candidate verification remains open.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- October 22: fixed six new Python dependency advisories; patched-lock audit is clean (86 runtime packages; npm also clean). See [dependency checkpoint](docs/release/DEPENDENCY-SECURITY-2026-10-22.md). Refresh on the final candidate.
- October 22: three-image build and Linux PDF/resource probes passed on bbd64be8; see [build checkpoint](docs/release/LOCAL-BUILD-2026-10-22.md). Refresh for the final candidate.
- October 22: compose and unauthenticated ZAP checks passed on 1d8e81e, including cleanup; ZAP retained one low/three informational alerts, no medium/high alerts. See [local checks](docs/release/LOCAL-CHECKS-2026-10-22.md).
- October 22: backend-disabled Terraform validation passed on clean bbd64be8 after a whitespace fix. No cloud state or resources changed.
- October 22: restore drill passed on 990edb17 after doctor fix: 720 tables, no lost rows, two verifier security events added; cleanup passed. See local checks above.


## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).

## Contract FX freshness at close — October 23, 2026

- Migration 0340 retains original FX inputs. Lock checks identify stale clean heads and the
  next close repairs them through FX_REPUBLISH, including approval/computation races.
- Two native races, the refused-post ordering and ordinary close/rerun pass; scoped lint/types
  and economic-input/privacy checks pass. No deployment. See CURRENT-DEVELOPMENT-SCOPE for bounds.
- October 24: privacy/schema audit gaps repaired; 29 targeted checks pass.
  See CURRENT-DEVELOPMENT-SCOPE for bounds; this is not a full-suite pass.
- Forecast re-export and close-assessment checkpoints moved to REPORTING-CHECKPOINTS-2026-10-22.

## Owner-selected shared estimates — October 23, 2026

Shared overrides local; breakage totals use SSP allocation; combination changes require effective-date
reassessment. Shared return-rate drafts now support frozen bindings, impact previews, independent
approval, atomic application/recomputation, effective-date exits and onboarding by common target
keys, version-specific targets and frozen cost FX. Breakage drafts now retain original-member
targets; previews use those targets and refuse changed populations/identities. SSP previews retain
dated FX. Dated preview passes native API verification; application and reassessment remain open. See
[checkpoint](docs/release/SHARED-TARGET-CHANGES-2026-10-23.md).

## Acquired reporting and locked continuation — October 24, 2026

Original cutover balances enter BUSINESS_COMBINATIONS with retained evidence and clickable
summary/member source explanations in all three currency views.
Principal ASC606 cross-entity close/lock and three-currency reruns pass. Native revision 20 adds
original cross-entity acquisition control sources, including foreign cutover snapshots. Mixed
groups, agents and recomputed baselines remain open. See
[checkpoint](docs/release/ACQUIRED-CLOSED-CUTOVER-2026-10-23.md).

## Aligned range reports across calendars — October 23, 2026

- Contract-balance and RPO rollforwards plus opening-liability revenue now accept separate
  calendars when both endpoints, every included period and the preceding period align exactly.
  Missing, reversed, discontinuous or different ranges retain the calendar refusal.
- Public combined monetary rows equal separate runs and reruns match; mixed-date guards and
  interval checks pass with scoped types/lint. No date reallocation or posting changes.
- Snapshot checkpoint archived. No deployment.

Oct 26: independent functional cost impairment, capped reversals and carrying/journal reconciliation implemented. See CURRENT-DEVELOPMENT-SCOPE. No deployment.
