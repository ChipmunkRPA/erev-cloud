# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Locked-period foreign invoice carry — October 20, 2026

- The populated foreign lock witness now also follows the no-reopen path: an EUR 4,000
  invoice dated August is recorded after the actual August lock, then September is closed
  through the public pipeline. Transaction, functional and reporting rollforwards all pass
  their balance tie-outs. The August lock remains the only lock/reopen record for its period.
- Frozen opening remains EUR 10,000 / USD 11,050; closing after the carried invoice is
  EUR 6,000 / USD 6,720. September's actual FX pass supplies USD 70 of remeasurement. Before
  that pass the functional report correctly reported the unposted difference; no residual
  or synthetic balancing entry was added to hide it. This closes the ordinary invoice/TIME
  carry acceptance gap using the existing implementation. Reconciliation review fixtures
  remain fixtures, not independent approval; no external GL trial balance is claimed.
- Still open: public combined-contract credit-memo and more complex carried EVENT correction
  scenarios, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Necessary verification is this actual lock/invoice/close/report flow plus scoped lint.
  No deployment and no claim that all Reporting or production readiness is complete.

## Credit-memo FX source attribution — October 20, 2026

- JET-10c attribution now resolves the original credit-memo difference trace into its
  retained liability reliefs, source owners, layer creation dates and event sequence.
  Each relief matches its original output and trace; the pinned rate and full difference
  formula are verified. Transaction portions are cumulatively converted in original trace
  order, preserving the once-rounded memo total and offsetting owner differences without a
  residual bucket or an allocation based on historical carrying value.
- Functional rollforward billing now uses the same retained spot conversion for those memo
  portions; actual posted EVENT FX adjusts each liability layer before its memo. Historical
  report bindings without the EVENT source path retain their former behavior. Derived source
  identities remain tied to immutable computation evidence and participate in paid-history
  subtraction. The engine and sealed journal amounts are unchanged.
- Necessary checks passed: actual single-layer and two-layer public memo/report workflows,
  ERP-imported and ENGINE-posted billing, source attribution and identical bound reruns. A
  USD 40,000 memo converts GBP 32,000 historical relief to GBP 33,600 at spot, with GBP 1,600
  FX and a GBP 40,000 closing liability. The two-layer full credit closes to zero with
  GBP 4,000 FX. Focused rounding/offsetting-owner and corruption checks, lint and types pass.
- Still open: public combined-contract credit-memo acceptance, late-carried public acceptance
  without reopening, recorded privacy/snapshot registry gaps and final accounting/release
  acceptance. This closes the ordinary JET-10c source gap, not every FX scenario. No deployment.

## Foreign lock-to-lock business attribution — October 20, 2026

- Difference replay now holds operational period states constant after verifying both original
  computations and frozen endpoints. A public reopen no longer blocks late-event attribution
  as an unsupported entity change. Entity, currency, book population and calendar dates remain
  strict; the evidence records entities.periods.states normalization and the final replay must
  still reproduce the later frozen money, including posted revenue.
- Control FX projection verifies the retained settlement formula when S12 emits a zero
  difference node without a movement row. It does not discard zero cumulative sums, so
  offsetting owners remain visible; altered rate evidence refuses.
- Necessary verification passed: actual foreign close/export/acknowledgement/lock, two-controller
  public reopen, EUR 4,000 late invoice, actual second close/lock, and public variance jobs in
  transaction, functional and reporting currency. Each attributes the asset reduction solely to
  LATE_EVENT (EUR 4,000 / USD 4,420 / EUR 4,000) and retains normalization evidence. Reviewed
  reconciliation rows are fixtures, not independent accounting approval. Scoped unit checks,
  lint and types pass. No deployment.
- Still open: credit-memo FX difference attribution (JET-10c has a retained difference trace
  but no remeasurement movement leaf), end-to-end late-carried public acceptance without
  reopening, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  This populated foreign two-lock witness does not establish every FX or membership scenario.

## Exact paid-origin window for carried FX — October 20, 2026

- TIME FX historical attribution now selects the target period plus its immediately preceding
  continuous closed/permanently-locked run, bounded by the retained anchor. It no longer treats
  every period between sparse calculation targets as paid: an intervening open period stops
  pooling, matching S14. EVENT/ALL retain their exact source origin. All period states come from
  the original encrypted computation input; today's calendar does not change reruns.
- Necessary verification covers sparse targets across an intervening open period, a retained
  anchor inside a locked run, EVENT origin isolation and refusal of TIME in a non-postable
  period; the existing actual multi-layer repeated-close/report scenario checks integration.
  Scoped lint/types pass. No deployment.
- Still open: end-to-end late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final accounting/release acceptance. Correcting
  this selector does not establish those broader acceptance cases or production readiness.

## Regrouped FX source ownership — October 20, 2026

- Historical FX matching now uses S14's retained-membership regrouping rule. A stored group
  subject is compared under the computation's original member population; keyless legacy
  lines use that retained group/entity subject. Neither the sealed ledger fields nor the
  original source calculation is rewritten. Command intent checks retain exact stored subjects;
  only a missing subject uses the historical fallback.
- Necessary checks cover keyless settlement attribution, the actual reversal after the listing
  member leaves a three-contract group, and a two-contract public functional report. The latter
  assigns GBP 1,080 to the actual asset owner even though the ledger lists another member.
  The regrouping reversal retains the original paid-line dependency and delivered owner.
  The public August–September report after exit nets original/reversal/reposted FX to USD 200
  and passes the balance tie-out. Scoped lint/type checks pass.
- Scope correction: current control FX templates JET-10a/b/c select one role on each side;
  S14 does not emit split-weight targets for these flows. Unknown split formulas still refuse,
  but are not an outstanding feature for the current FX report path.
- Still open: late-carried public acceptance, populated foreign two-lock
  acceptance, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Group settlement/exit cases do not establish every membership transition or production
  readiness. No deployment.

## Source-timed EVENT FX reporting — October 20, 2026

- Functional/reporting rollforwards now consume actual command EVENT posting deltas with
  original event sequence, source key, owner and asset/liability layer. Original and correcting
  postings net by dated source before walking the balance path. Billing settlement precedes
  its invoice; relief FX precedes revenue. New reports remove both old synthetic settlement
  movements, avoiding duplicate timing. Historical bindings retain the original path.
- New event_posted_fx_v1 bindings retain every command line, recursive paid dependency and
  evidence hash. Report execution rechecks its requester before authorized computation reads;
  close snapshots retain the restricted read-only SYSTEM path. Migration 0194 documents these
  source tables and semantics in the report IPE catalogue.
- Necessary checks: ERP and ENGINE foreign invoice rollforwards with source bindings and
  identical reruns; repeated liability close; command reversal and its net-zero report; scoped
  projection/path/catalogue checks and lint/types. No deployment.
- Still open: split-target formulas, regrouped/keyless historical subjects, combined-membership
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded privacy/
  snapshot registry gaps and final accounting/release acceptance. These ordinary settlement
  cases do not establish production readiness or all Reporting requirements.

## Contract-computation FX evidence — October 20, 2026

- The shared FX attribution reader now adapts original command-computation input/output
  evidence as well as close-pass envelopes. It authorizes the complete retained group,
  verifies the encrypted source hashes, version trace and exact posting intent, and uses
  the original per-book seal cutoff to select historical paid lines. Version evidence keeps
  its real version identity; no synthetic close record or current-rate reconstruction is used.
- Paid attribution now follows actual command settlement and reversal histories recursively.
  Necessary checks passed: actual GBP 1,080 settlement and GBP 540 reversal with the original
  paid-line identity and both computation evidence hashes, plus scoped lint/types.
- Still open: public rollforward EVENT settlement timing must consume these sources without
  duplicating the existing before-invoice settlement flow and period-end offset. The TIME
  report path is unchanged. Split targets, regrouped/keyless historical subjects, combined
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded registry
  gaps and final accounting/release acceptance remain open. No deployment or readiness claim.

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
