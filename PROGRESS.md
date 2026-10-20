# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Retained revenue history for close passes — October 20, 2026

- Real period-end passes now freeze revenue paid-line identities and both original currency
  amounts alongside the existing FX population. The populations are distinct and covered by
  the same immutable encrypted evidence file and hash; an empty revenue population is explicit.
- Revenue attribution reads original close-pass evidence before falling back to ordinary
  computation evidence. A close pass lacking the new revenue population is refused instead
  of treating absent history as zero. Ledger role, selected line and retained hashes remain
  checked; recursive original-owner attribution and both currency views use the shared reader.
- Necessary checks passed: a real close release retains all original group revenue lines and
  their transaction/functional amounts; the existing FX close remains immutable/idempotent;
  combined-member deliveries, returns and report reruns remain correct. Three integration
  scenarios and scoped lint/types passed. No deployment.
- This completes capture/reader integration, not all close revenue scenarios. A nonzero
  close-only revenue posting still needs an end-to-end attribution scenario; mixed TIME/EVENT,
  intercompany reversal and asset/new-liability presentation remain open, as do the other
  documented feature/release gaps and independent accounting sign-off.

## Transaction-currency revenue reversal disclosure — October 20, 2026

- Ordinary transaction opening-liability disclosure now attributes negative revenue through
  original signed transaction source quantities and recursively verified paid lines. Original
  layer creation dates identify opening consumption; the recognizing member is not capped by
  its own opening balance. Reversal groups still must reconcile their complete control path.
- The shared source projection retains signed integer coefficients independently of rounded
  functional amounts, so a zero functional source does not erase a nonzero transaction amount
  or reverse its sign. No inverse FX conversion is used. Original layer dates are reconciled
  across historical computations; attribution caches cannot mix currency views.
- Reversal method, source identities, creation dates, paid lines and evidence hashes are bound
  for rerun, with an explanatory footnote. Earlier bindings retain their original builder;
  intercompany transaction reversals retain the earlier path pending counterpart attribution.
  Migration 0201 updates the disclosure IPE description.
- Necessary checks passed: the real combined-member delivery/return sequence reports
  USD 58,500 transaction revenue and opening relief, alongside GBP 46,800 functional values;
  transaction, functional and reporting reruns match. Existing single-contract results and
  catalogue migration pass. Fifteen source/delta checks, including zero-rounded source signs,
  and lint/types pass. No deployment.
- Still open: intercompany reversal attribution, mixed TIME/EVENT source allocation,
  close-pass-only revenue histories, asset/new-liability reversal presentation, per-obligation
  opening consumption and complex membership/carry histories. Final release verification
  and independent accounting acceptance remain open; Reporting is not yet complete.

## Cross-member revenue reversals through original posting history — October 20, 2026

- Ordinary revenue attribution now reads original transaction targets and their separately
  retained functional amounts, projects original owner/layer sources, and recursively
  subtracts the exact sealed paid-line population. Original role, period, TIME basis,
  ledger fields, computation hashes and all target/paid/delta amounts must agree. A shared
  per-report cache avoids repeatedly replaying the same immutable paid history.
- Live functional/reporting rollforwards and opening-liability disclosures use this proof
  for ordinary cross-member revenue. Source-proven reversals are now accepted when the
  complete posted owner/layer relief population equals the retained consumed-layer history.
  Dependencies and signed movements are retained for rerun. Earlier bindings keep their
  original path; intercompany entries retain their prior calculation and reversal limits.
- Necessary public scenario passes: three deliveries across two periods retain the prior
  same-period posting; a subsequent return reverses the original opening-layer owner's
  revenue. GBP 50,400 falls to GBP 46,800 for both recognized revenue and opening relief.
  Functional and reporting views rerun identically. Catalogue migration 0200, lint and types
  pass. No deployment.
- Still open: transaction disclosure reversal attribution, mixed TIME/EVENT functional
  source allocation, close-pass-only revenue history, asset/new-liability source presentation,
  per-obligation opening consumption and complex membership transitions. This completes the
  tested ordinary liability-backed return path, not every negative-revenue scenario.
  Final release verification and independent accounting acceptance remain open.

## Revenue posting-delta evidence and reconciliation — October 20, 2026

- Added revenue-line evidence reading alongside the existing FX adapter. It verifies the
  line against exactly one original retained posting intent in transaction and functional
  currency, verifies the trace/output and sealed posting, and captures the original
  pre-computation revenue population by ledger cutoff. Later/current lines are excluded.
- Added exact source-level target minus prior target minus paid reconciliation, including
  TIME, EVENT and ALL bases, negative amounts and owner-preserving cancellation across
  computation versions. Target totals, TIME components, paid totals and final delta are
  each checked. Source date and source key now accompany the signed layer projection.
- Ordinary revenue posting trace nodes are transaction-currency nodes; their functional
  amounts are separately retained. The reconciler therefore accepts verified explicit
  target facts rather than treating the transaction trace as a functional FX delta.
- Necessary checks passed: 14 focused source/delta checks and a real combined-contract
  sequence proving the later revenue envelope includes the prior posting but excludes its
  own posting; incorrect functional amounts are refused. Existing report reruns pass.
- Still required: wire verified functional target/time projections and recursive paid
  attribution into report presentation, including close-pass revenue histories. This
  internal reconciliation/reader addition does not yet enable complete negative-revenue
  reports. Per-obligation opening consumption, asset presentation transfers and final
  accounting/release acceptance remain open. No deployment.

## Signed revenue calculation sources — October 20, 2026

- Added exact signed expansion of retained S12 revenue cumulative targets, preserving each
  original movement, owner, layer and kind. The reader handles liability consumption, asset
  creation, asset settlement and liability creation, including negative contributions and
  opposing owners at a zero net target. Every intermediate total must reproduce its trace;
  missing, duplicate, cyclic, changed-amount or wrong-currency sources are refused.
- Combined-member revenue attribution now verifies selected relief against the complete
  signed target. New runs retain the source projection and movement population for rerun;
  existing bindings retain their earlier validation path. This connects the source reader
  to live rollforward and opening-liability disclosures rather than a standalone calculator.
- Necessary checks: real cross-member functional/reporting disclosures and bound reruns;
  six signed-source/corruption checks; lint and types. No deployment.
- This is the source expansion needed for further posting-delta work, not completion of
  negative-revenue reporting. Original/prior target and paid-history reconciliation, asset
  presentation transfers, per-obligation opening consumption and complex carried histories
  remain open. Final release verification and independent accounting acceptance remain open.

## Reporting and forecast data catalogue reconciliation — October 20, 2026

- Classified the 43 missing code columns across retained evidence-sample dependencies,
  forecast actuals captures, scenario refresh records, ordered inputs and import replay
  mappings. Business payloads remain confidential financial data; identifiers and lifecycle
  metadata follow the existing registry rules. Existing retention categories are preserved;
  proposed classifications still require owner acceptance, not implied legal approval.
- Added the missing scenario-refresh model section and explicit sample dependency columns;
  documented frozen import mappings. The catalogue now matches all 174 documented tables
  and every implemented column. Updated the strict documentation reader for the existing
  four-column table format and reconciled document order.
- Snapshot checks now explicitly verify that copied imports clear the regenerated forecast
  input-set reference and source-only mapping without mutating source data. The recorded
  reference-count/excluded-column drift and privacy registry failures are resolved:
  76 targeted catalogue and snapshot checks pass. No database migration or deployment.
- Remaining Reporting work is unchanged: original negative-revenue reversal attribution,
  per-obligation opening consumption, complex cross-member asset/carried histories and
  pre-close FX paths. Final release checks and independent accounting acceptance are open.

## Transaction opening-liability group consumption — October 20, 2026

- Positive transaction RPT-04 now pools control flows by retained computation version,
  entity and currency, assigning actual opening-layer consumption to the recognizing
  member. Earlier credit-memo debits reduce the available opening layer. Opening holders
  remain visible even when another member recognizes the revenue; groups and source
  method are retained for identical reruns. Migration 0199 updates the IPE description.
- Necessary verification: the combined-member disclosure reports USD 54,000 opening relief
  for an August-start range and zero for a July-start range, with unchanged USD 54,000
  recognized revenue and identical bound reruns. Existing single-contract results pass.
  All 28 control-path unit checks pass, including credit-memo consumption before revenue;
  implementation lint and types pass.
- Negative transaction revenue deliberately retains the existing net-reversal calculation;
  original reversal-source attribution remains unfinished. Per-obligation consumption,
  cross-member asset-creating/carried/other-control histories, pre-close unposted FX paths,
  recorded registry gaps and final accounting/release acceptance remain open. Reporting
  is not yet complete. No deployment.

## Opening-liability disclosure in functional/reporting currency — October 20, 2026

- New functional/reporting revenue_from_opening_liability requests now consume the retained
  balance path and original opening-layer attribution instead of silently reading amount_txn.
  Reporting openings use preceding closing rates; revenue flows use their period averages.
  The method, source populations and rates are bound for rerun. Earlier bindings keep their
  prior builder path; the transaction view is still the separate legacy implementation.
- The disclosure includes opening holders and recognizing members without capping a
  recognizer's valid combined-group relief at its own zero opening. Its footnote explains
  that distinction. Member/period source paths must reconcile before the disclosure is
  emitted, so unmatched paths cannot silently become disclosure totals. The IPE catalogue,
  source contract and migration 0198 document the additional sources and currency semantics.
- Necessary public checks passed: standalone disclosure totals and contract details equal
  the corresponding functional/reporting rollforward relief in the combined-member case,
  including GBP 43,200 recognized against another member's opening. July-start versus
  August-start ranges change opening/current provenance without changing recognized revenue.
  Reporting currency, summary opening totals and identical bound reruns pass; lint/types pass.
  No deployment.
- Still open: the transaction disclosure's legacy same-contract cap, per-obligation opening
  consumption, cross-member asset-creating/reversing/carried/other-control histories and the
  underlying posting-delta replay gaps. This new disclosure path currently requires reconciled
  source balance movements; pre-close paths with unposted FX are not accepted. Recorded
  registry gaps and final accounting/release acceptance remain; Reporting is not complete.

## Cross-member revenue relief and opening provenance — October 20, 2026

- Added retained positive-revenue layer transfers for combined members. The original trace
  identifies the recognizing contract while the movement keeps the consumed layer's owner.
  All liability reliefs must reproduce the affected recipient's entire posted revenue in
  every selected period before any transfer is admitted. Original lines, relief/creation
  movements, amounts and opening portions are bound for rerun. No remainder is inferred.
- The v3 member bridge includes those source transfers and classifies revenue by the actual
  consumed layer's creation date, not the recognizing member's own billing history. v1/v2
  bindings retain their original paths. Migration 0197 updates the rollforward IPE catalogue.
- Necessary public checks passed: another member recognizes USD 54,000 revenue using GBP
  43,200 of the first member's July advance; differing historical-rate member closings are
  GBP 74,571.43 / 29,828.57 with +2,571.43 / -2,571.43 reclassification and zero OTHER. Functional,
  monthly reporting and bound reruns pass. An August-start range classifies the GBP 43,200 as
  opening relief; a July-start range classifies it as current-range relief without changing
  total revenue or closing balances. Scoped lint/types pass. No deployment.
- Still open: the separate revenue_from_opening_liability builder reads amount_txn and applies
  its legacy same-contract cap; it must consume the multi-currency/source-backed relief path.
  Cross-member asset-creating, reversing, carried and other-control histories need their own
  posting-delta replay; this path requires full positive liability-relief reproduction and
  refuses unmatched histories. Recorded registry gaps and final accounting/release acceptance
  also remain. This is not full Reporting or production-readiness acceptance.

## Endpoint-driven member liability presentation — October 20, 2026

- New functional/reporting builds apply the retained member-presentation bridge to all
  foreign contract/entity endpoints, including periods without a memo or FX journal. This
  explains historical-rate reallocations when another member adds billing. The v2 binding
  records entity-qualified endpoint identities; v1 reruns retain their memo-triggered scope.
  Cache and member selection now distinguish entities so one contract cannot borrow another
  entity's carrying or presentation evidence. Migration 0196 updates the IPE description.
- Necessary checks passed: an actual two-member group with USD 90,000 advances at GBP rates
  0.80 and 0.84, no credit memo and no FX journal. Both members close at GBP 73,800; the
  independently sourced reclassifications are +1,800 / -1,800, and both OTHER amounts are zero.
  Functional and reporting views across August–September and their bound reruns pass. The
  existing monetary multi-layer repeated-close/report flow also passes under the broader
  source scope. Scoped lint/types pass; no deployment.
- Still open: cross-member revenue/other control-flow source transfers, more complex carried
  EVENT corrections and membership transitions, recorded privacy/snapshot registry gaps and
  final accounting/release acceptance. Generalizing the endpoint trigger does not establish
  those separate source-flow cases or production readiness.

## Combined-member credit-memo presentation — October 20, 2026

- Functional billing now reads source layers across the report's authorized members of the
  same immutable group version and entity. A credit memo can therefore price a relief whose
  layer belongs to another member, retaining the real source owner and movement identities.
- Added a combined-liability presentation bridge for in-range cross-member memos. It computes
  each endpoint's original layer carrying versus the engine's member presentation, then adds
  the known memo issuer/source transfers. Each original computation group must conserve zero.
  The independently derived amounts appear as RECLASSIFICATIONS; no amount is inferred from
  OTHER. Bound endpoint facts, movements and transfers are checked on rerun, including monthly
  reporting-currency paths. Historical bindings without the bridge retain the previous path.
- Fixed a separate false-PASS: unexplained OTHER on an individual contract now fails the
  movement tie-out even when opposing contract errors cancel in the currency total. Migration
  0195 and the IPE catalogue describe the expanded source scope, bridge and per-contract check.
- Necessary checks passed: public two-member memo consuming another member's layer, same and
  different historical rates, exact member closing/reclassification amounts, bound reruns,
  reporting-currency monthly projection, 27 scoped path checks and lint/types. The differing
  rate case closes at GBP 74,314.29 / 41,285.71 with GBP +714.29 / -714.29 reclassification;
  every member has zero unexplained OTHER. No deployment.
- Still open: general member reallocations without an in-range cross-member memo, more complex
  carried EVENT corrections, recorded privacy/snapshot registry gaps and final accounting/
  release acceptance. These cases do not establish every membership transition or readiness.

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
