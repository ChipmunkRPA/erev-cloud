# Archived Reporting checkpoints — October 22, 2026

## BBR reporting currency — October 22, 2026

- Reporting view now values all four measures at retained entity-period average rates after
  original functional valuation. Signed source pennies match period totals; journal comparison
  uses the same aggregation basis. Cells disclose rates and original functional amounts.
- Migration 0334 records scope. Eleven BBR unit cases and a populated USD/GBP public report,
  cell and retained-rerun workflow pass, with scoped lint/types and metadata parity. No deployment.

## Waterfall calendar columns — October 22, 2026

- New runs align whole reporting intervals by actual dates and retain entity-local period
  mappings. Same dates combine; differing boundaries remain separate labelled columns, with
  matching cell sources. Matching layouts and older saved runs preserve their prior shape.
- Migration 0333 pins IPE metadata. Necessary validation: 14 waterfall unit cases, populated
  report/retained-rerun workflow, date-label frontend case, scoped lint/types and metadata parity.
  No partial-period allocation or change to native amounts; no deployment.


## Modification amount source drill — October 22, 2026

- Money cells rebuild saved inputs and link original native trace nodes. Analytical equivalents
  show pinned spot/average rates separately. Retained UUIDs resolve source visibility only;
  old runs without identity, missing cells and scope changes refuse. Internal-link filtering
  rejects external/API destinations. Migration 0332 freezes IPE metadata.
- Necessary checks: 22 register and eight catalogue cases, populated K02 source/component/
  catch-up/spot/reporting drills and refusals, four frontend cases, scoped lint/types and
  metadata parity. No deployment; per-event functional posting ownership remains open.

## Optional per-event close variance — October 22, 2026

- Added Attribution detail: By driver (default) / By event. Detailed mode executes each business
  event in ENG-06 order, retaining individual signed changes and execution hashes. Driver totals
  and frozen monetary endpoints still reconcile; reference/FX and membership/population phases
  remain explicit. No proportional split or journal-posting ownership is claimed.
- Ordinary and membership replay share the detailed-boundary implementation. A retained choice
  is checked at prepare/rebuild and contributor reads; old/default runs keep grouped behavior.
  Migration 0331 freezes schema/IPE metadata; the existing toolbar exposes labelled choices.
- Necessary verification: 46 replay/catalogue cases, plus two new native net-zero modification
  variants (USD and GBP), eight toolbar cases, and the event-mode worker/bound-rerun workflow
  with real empty lock snapshots. Native positive/negative effects are checked against grouped
  totals; membership functional endpoints also match. Scoped lint/types and metadata parity pass.
- Original per-event journal ownership in the modification register remains open. This completes
  a user-selectable causal replay capability, not that separate feature. No deployment.

## GL automatic certification — October 23, 2026

- Attached GL comparisons now use published kind-specific rules for automatic certification.
  Only complete, nonempty zero-variance comparisons qualify; no policy is created automatically.
  Write-once rule IDs, CTL-025/026 and audit evidence retain the decision (migration 0337).
- Two populated GL/billing workflows and transition parity checks pass; scoped lint/types pass.
  See CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Secondary-book late-event reporting — October 23, 2026

- New computations record late-event evidence separately for each enabled entity book, with
  that book's posting period. The register reads secondary identities without duplicating the
  primary row; historical evidence and saved reports stay unchanged (migration 0338).
- Two producer cases, the extended K07 report workflow and eight catalogue cases pass;
  metadata equality and scoped lint/types pass. Scope and test boundaries are recorded in
  CURRENT-DEVELOPMENT-SCOPE.md. No deployment.

## Cross-calendar revenue disaggregation — October 23, 2026

- New runs combine only identical actual date intervals, with separate columns for different
  periods and retained entity/local-period mappings. Same-calendar labels and legacy bindings
  keep their existing interpretation. No partial-period reallocation (migration 0339).
- Populated mixed-calendar totals and saved reruns, existing journal tie-out and currency
  workflows, two interval-layout cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- Earlier GL checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Cross-calendar waterfall selections — October 23, 2026

- Explicit fiscal-key ranges now reach the existing date-aligned waterfall implementation.
  Each entity's local intervals and contributor sources stay distinct; month/quarter/year
  totals and retained reruns match separate entity reports. Other report guards remain.
- Three populated API/cell/rerun workflows and the remaining guard check pass; existing
  date-bucket unit cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- Earlier late-event checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Original forecast report re-export — October 23, 2026

- Original forecast reports now accept the rerun API, binding the verified saved publication
  through the catalogue adapter without recomputing the forecast. Existing UI flow is unchanged.
- Populated forecast lifecycle passes: JSON/CSV/XLSX original and catalogue reruns preserve
  dataset hashes and bound sources; source-access checks remain. Scoped lint/types pass.

## VC / royalty close assessment controls — October 23, 2026

- Final close passes now persist native reassessment/accrual gaps as blocking exceptions with
  book/period scope and input hashes. Successful rechecks settle only superseded findings;
  no extra engine pass or approval workflow. Existing engine coverage limits remain explicit.
- Normal close and injected-gap lifecycle workflows pass, including cross-book gate isolation
  and settlement; two native gap cases and scoped lint/types pass. See CURRENT-DEVELOPMENT-SCOPE.
- UI follow-through: VC counts/links use the same book-specific blocking scope; element banners
  recognize generated findings and retain in-progress items; royalty titles are readable.
  Extended backend lifecycle and two focused UI cases pass, with frontend types/lint.
- Earlier disaggregation checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md. No deployment.

## Publication checks and backlog audit — October 23, 2026

- On 47db35bf: secrets scan 4,183 files / nine allow-lists / zero findings; runtime licence
  check 142 packages / eight allow-lists / zero findings. Research directories remain untracked;
  PolyForm Noncommercial remains intact. No deployment.
- Confirmed existing unassigned-approval alerts and warning UI; historical C-6 is superseded by
  the October 7 B1-15 completion. B2-2/C-7 was reproduced and repaired below.
- Earlier waterfall checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Privacy field catalogue — October 23, 2026

- Reconciled all 11 missing columns: historical commit identity/timing evidence and modification
  termination terms, with matching data-model declarations. All 12 catalogue checks pass.
- Export permissions and retention execution are unchanged. The separate revision-0166 schema
  parser issue remains open. This supersedes the privacy omission in the preceding checkpoint.

## Migration/schema verification — October 23, 2026

- Fixed multiline constraint and quoted-comma parsing; full migration-chain comparison now runs.
  Corrected document-only primary-key/default/header omissions; no runtime schema change.
- Ten architecture and twelve privacy checks pass, including mismatch-detection witnesses.
  Supersedes the previous parser gap. Release-candidate verification remains outstanding.
- Publication audit checkpoint moved to REPORTING-CHECKPOINTS-2026-10-22.md.

## Modification causal reporting — October 22, 2026

- Owner-selected sequential causal analysis is now exposed in the modification register.
  Baseline, selected/other event effects and final period revenue reconcile in transaction,
  functional and reporting views. Cells retain execution evidence; saved reruns preserve results.
- Migration 0335; nine native causal cases, 40 existing replay cases, two populated public
  workflows and ten frontend cases pass, with scoped lint/types. No posting-rule change or deployment.
- BBR reporting currency (0334) and waterfall calendar columns (0333) checkpoints moved to
  REPORTING-CHECKPOINTS-2026-10-22.md; current scope remains in CURRENT-DEVELOPMENT-SCOPE.

## Close-variance offsetting effects — October 22, 2026

- Retain contract rows whose nonzero replay effects offset to zero, including repeated runs
  of one driver. Retain driver summary rows when opposing contract contributions net to zero.
  Unchanged replays still render empty; section totals remain the original net amounts.
- Drill evidence includes signed intermediate effects and event references. The cell reader
  checks each retained effect population against its contract/driver amount before displaying it;
  original source/hash/entity checks remain. New bindings pin offset details; older bound runs
  preserve their original row population and evidence without the additive details works.
- Migration 0330 documents the presentation scope. Necessary checks cover native replay/export
  compatibility, authored offset witnesses, contributor reads, corrupt effects, catalogue parity
  and scoped types/lint. No engine calculation, event grouping or deployment changed.
- Individual amounts within a consecutive same-driver event run remain an implementation gap.

## Modification functional calculation evidence — October 22, 2026

- New register runs expose original functional catch-up calculations and period/basis when a
  single event explains the full native period flow. Historical FX pieces and both currency
  totals are verified; trace hashes/node identities and resolved values remain in retained inputs.
- Columns distinguish native calculation from spot equivalents and journal posting deltas.
  Mixed/missing evidence stays empty; older bound runs keep their columns. Migration 0329
  records the scope. No native monetary calculation or deployment changed.
- Necessary checks: 36 focused reader/register/catalogue cases, native USD/GBP positive and
  negative catch-ups, mixed-period and corrupt-source refusals; existing populated register,
  approved-rate and mixed-period API workflows, plus retained reconstruction and scoped lint/types.
- Multi-event functional allocation and actual per-event posted deltas remain open; this is
  incremental calculation evidence, not completion of that larger feature.


## Portfolio storage foundation — October 23, 2026

- Revision 0341 adds named portfolios and retained member intervals, tenant foreign keys,
  overlap prevention, once-only closure and populated-downgrade protection.
- Snapshot datasets include both tables and references; record cutoffs omit future closure.
  Schema/privacy, dataset and focused database checks cover this foundation.
- Shared estimates are NOT complete: commands/UI, approval fan-out, member calculations,
  reporting and populated restore remain. Engine portfolio returns can be reused; breakage
  still selects contract-only estimates. Two estimation choices await the owner's response.


## Material-right product defaults — October 23, 2026

- POL-026 now initializes option entry from resolved product policy, using retained pins
  when present. API omission resolves the common book default; explicit methods win.
  Conflicting defaults require a choice. Saved immutable terms govern later calculations.
- Public entry/rollback/activation and two explicit discount workflows pass; two resolution
  and 18 UI cases pass, with scoped lint/types and regenerated API types. No deployment.
- Remaining policy implementation: portfolio estimates (POL-015) and lessor combination
  (POL-231). This supersedes POL-026 in the preceding reader audit.


## Portfolio management — October 23, 2026

- Added public portfolio/member commands and Settings → Reference data → Portfolios.
  Create/edit, search/add, reasoned exit and retained history are available with pagination.
- Parent ETags, audit facts and contract/entity permissions protect writes; reads/counts omit
  hidden members. Stale metadata edits stay visible until the user explicitly reloads.
- Populated API workflow, four UI cases, 24 route checks and scoped lint/types pass; existing
  computation head is unchanged. Shared estimate application remains.
- Actual copy and LATEST refresh jobs now preserve populated member history; a successor
  sandbox membership edit leaves production unchanged. The focused database workflow passes.
  Two previously asked estimation choices still await the owner. No deployment.
