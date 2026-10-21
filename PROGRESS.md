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

## Adoption Bridge supplied legacy carrying balances — October 21, 2026

- Added optional per-contract legacy functional liability/unbilled carrying inputs to the public
  report API and an editable row-based UI. Each row requires a source reference, prior period-end
  date and entity functional currency. These are explicitly labelled supplied report evidence,
  retained with the run; they do not post or change the LEGACY ledger.
- Inputs must identify distinct contracts within the authorized endpoint population. Invalid dates,
  currencies, negative/nonfinite/overprecision amounts, missing references, unknown nested fields
  and simultaneous positive net liability/unbilled positions are rejected. Transaction currency
  refuses functional inputs. Uncovered foreign contracts and their affected totals remain unknown.
- Reporting translates supplied positions independently at the closing rate, preserving historical
  income translation. The UI can reopen saved structured parameters; retained reruns preserve
  values, source references and output hashes after later revenue events.
- Necessary verification passed: 61 focused builder/source-binding cases, 6 toolbar cases, public
  foreign functional/reporting/replay flow, original transaction disclosures, migration metadata
  parity, scoped lint and types. EUR 123,456.78 at closing 3 yields USD 370,370.34; supplied balances
  remain distinct from billed-less-revenue estimates. Migration 0301 adds the public schema.
- Remaining: other documented report adapters and final repository verification. This completes
  the carrying-position input path; the system does not obtain or independently certify the
  referenced external historical balance evidence. No deployment.

## Adoption Bridge retained same-source replay — October 21, 2026

- New transaction, functional and reporting runs retain per-contract comparison inputs,
  final legacy-only population, selected/resolved application date, currency basis and source/FX
  evidence. Bound reruns reconstruct sections, position comparisons, missing-position messages,
  membership counts and totals without consulting current books, labels, ledgers, traces or rates.
- Retained input admission checks tenant, entity set, currency view, requested date and contract
  selection. Decimal amounts and separately translated legacy positions are restored before
  aggregation. Legacy ledger line IDs are captured alongside the selected primary versions.
  Migration 0300 describes the retained basis; older OPEN runs keep new-evaluation semantics.
- Public verification: append another USD 1,000 of December 2025 legacy revenue through the
  normal event API and recompute; fresh transaction, functional and reporting rows all change.
  All three original runs then rebuild identical rows and output hashes. Input-only tests have
  no database session, recompute totals after a retained amount changes, preserve legacy-only
  counts/unknown positions/closing-translated positions and reject scope/selection mismatches.
- Necessary checks: 51 focused report/source-binding tests, public foreign replay, original
  transaction disclosure, catalogue migration parity and scoped lint/types passed. No deployment.
- Remaining: historical foreign legacy carrying-position inputs, other documented report
  adapters and final repository verification. Adoption same-source replay is now implemented;
  foreign legacy positions are still unavailable when their historical carrying evidence is absent.

## Adoption Bridge reporting-currency view — October 21, 2026

- Added Reporting currency to the public report and frozen migration 0299. The builder reads
  each historical functional cumulative-income endpoint, translates each period's movement at
  its approved average rate and accumulates those translated movements. Ending primary and
  available legacy positions use the ending closing rate independently of income. Explicit
  legacy position values prevent billed-at-closing minus historical revenue from inventing a
  different balance. Included/legacy-only population is determined at the final endpoint.
- Period-average and closing rate inputs are recorded separately. Missing/ambiguous rates are
  refused through the shared approved-rate admission; unknown foreign legacy positions remain
  unavailable at contract and aggregate level. A nonzero imported opening-revenue node actually
  consumed by the revenue trace is refused for foreign reporting translation when its historical
  period allocation is absent; it is never treated as first-period income. Identity conversion
  does not require that historical FX allocation.
- Public flow verified with recorded EUR income: January-November EUR/USD average 1, December
  average 2 and closing 3 produce USD 160,000 legacy revenue, 178,666.66 primary revenue,
  18,666.66 cumulative effect and 192,000 primary liability. This distinguishes period income
  conversion from both ending-average and closing-rate shortcuts. The FX service generates
  inverse rows, so the test approves a new version of the existing pair's set instead of
  introducing duplicate simultaneously approved rates.
- Necessary validation: public foreign reporting and original transaction flows, schema/IPE
  migration parity, 48 focused report/source-binding cases and scoped lint/types passed.
  Remaining: foreign legacy carrying-position sources, Adoption retained same-source replay,
  other documented adapters and final repository verification. No deployment.

## Adoption Bridge functional view — October 21, 2026

- Added Transaction/Functional selection to the public report (migration 0298). Functional
  revenue uses posted LEGACY amounts and dated primary revenue nodes whose original transaction
  quantity/currency must reconcile to the stage 09 population. Stage 12 now retains that quantity
  beside cumulative functional revenue; missing, stale or mismatched foreign evidence is refused.
  Primary balances use the shared dated member-balance projection, preserving historical layers.
- Foreign LEGACY liability/unbilled carrying evidence is still absent. Affected contract cells
  and currency-level comparison totals/effects are unavailable with an explicit basis message
  and count, rather than substituted transaction amounts, false zeroes or partial totals.
  Same-currency and transaction-view comparisons retain their complete existing behavior.
- The full public foreign workflow found and fixed an output-boundary omission: LEGACY
  BookOutput now preserves JET-15 line rate references, which database persistence requires.
  Engine-only posting tests had not covered that boundary. A regression now checks assembly,
  and approved foreign events successfully compute, persist and appear in the report.
- Necessary validation: public USD/EUR case shows legacy EUR 80,000, primary EUR 176,000,
  cumulative effect EUR 96,000 and primary liability EUR 64,000; historical legacy positions
  remain explicitly unavailable. Original transaction disclosure, schema/IPE migration parity,
  45 focused report/source-binding cases, eight LEGACY cases and scoped lint/types pass.
- Remaining: foreign legacy carrying-position sources, reporting-currency translation, Adoption
  same-source reconstruction, other documented report adapters and final repository validation.
  This completes the usable functional income/primary-balance view, not all multi-currency work.
  No deployment or real-business migration requirements were added.

## Foreign LEGACY revenue and JET-15 — October 21, 2026

- Fixed foreign pre-standard revenue failing at JET-15 because the LEGACY fold supplied only
  transaction amounts. It now converts each signed source event at its effective-date pinned
  spot and accumulates those historical functional amounts by obligation/period. Stage 14
  consumes the matching functional target and rate references; no framework recognition or
  FX-layer stages are run for LEGACY. Same-currency behavior remains unchanged.
- Registered replayable books.legacy_fx.v1 nodes cite both the original event amount and rate;
  Explain includes the conversion date. Missing FX produces an FX_RATE_MISSING finding naming
  the event and produces no partial LEGACY posting. Subsequent rates do not revalue prior income.
- Verified real JET-15: USD 1,200 at EUR 0.80 posts EUR 960; a USD 200 reversal at 0.90 posts
  EUR 180, leaving EUR 780. A full USD 1,200 reversal leaves zero transaction cumulative revenue
  and EUR -120 historical functional activity; that difference is retained. All journal lines
  balance in both currencies and traces re-evaluate. 38 book/legacy tests plus formula ownership
  and scoped lint/types passed. No schema changes or deployment.
- Adoption Bridge still needs the functional view wired to these recorded legacy amounts and
  dated primary amounts, with a defensible legacy-position basis, plus reporting-currency
  translation and retained reconstruction. This fixes a real foreign-currency posting blocker;
  it does not declare the report's multi-currency work complete.

## Adoption currency groundwork: dated billing evidence — October 21, 2026

- Stage 12 now retains cumulative billed-control functional activity by contract/entity and
  period, with the signed transaction quantity/currency/minor unit alongside it. Each movement
  records the admitted billing date, pinned spot-rate inputs and exact conversion; cumulative
  nodes replay from signed movements and prior periods. These are disclosure trace nodes,
  not new posting targets or replacement liability balances.
- Credit memos use their own dated spot rather than the carrying amount of the historical
  liability layer consumed. Verified example: EUR 1,000 at 1.10 plus EUR 500 at 1.20 less
  EUR 200 credit at 1.30 gives USD 1,440 cumulative activity, while the old layer relief is
  USD 220. Later closing rates do not rewrite the historical activity. Contract members
  remain separate and POL-160 receipt/due-date selection is preserved.
- Necessary verification: 12 layer cases, 40 related functional/remeasurement/real book-replay
  cases, and a full-engine trace-boundary assertion passed, plus scoped lint/types. No database
  or posting schema changes; no deployment. New trace evidence changes computation content;
  older computations are not backfilled and exact-original replay retains its mismatch guard.
- Adoption Bridge multi-currency remains incomplete. The new control-flow population must
  reconcile to stage 10 billed totals before use. LEGACY is a revenue-only fold with no stage
  12 balances; its historical functional revenue/position basis and reporting-period translation
  still need implementation. Do not derive a legacy liability merely by subtracting converted
  activity where FX settlement/carrying differences exist, or substitute a current closing rate.

## Intercompany Pairs retained reconstruction — October 21, 2026

- Transaction, functional and reporting runs now retain consumed ledger IDs, per-line amounts,
  entity/currency scope and FX evidence. Same-source reruns rebuild pairs, contract details,
  totals and unmatched tie-outs without reading current ledger lines, entity labels or rates.
  Tenant/entity/view/book checks remain; mixed functional currencies and out-of-scope sides
  remain incomparable rather than becoming false zeroes. Older OPEN runs retain their original
  new-evaluation semantics. Migration 0297 updates the report's IPE description.
- Public workflow verification: approving September GBP/USD average 1.30 instead of 1.28 changes
  fresh reporting due-to from USD 6,131.98 to 6,227.79; original transaction, functional,
  reporting and partial-scope runs retain identical rows/output hashes. Input-only tests rebuild
  without a database and recompute after changing inputs. 43 focused unit checks and scoped
  lint/types passed; catalogue migration parity verified. No deployment.
- Remaining: Adoption Bridge currency support, non-policy/book-context difference residuals,
  other documented report adapters and final repository validation. Intercompany Pairs
  retained reconstruction is complete; this does not claim all Reporting work is finished.

## Licence renewal recognition and advance-FX attribution — October 21, 2026

- Fixed two connected engine gaps found through full book-bridge replay: stage 06 now tells
  stage 03 when an added line belongs to RENEWAL/EARLY_RENEWAL, and the installed obligation
  preserves the draft's recognition_start_date. Previously the boundary dropped that guard,
  causing ASC606 to recognize a delivered future-term renewal immediately like IFRS15.
- Full-engine evidence now shows the discounted USD 900 licence renewal agreed/delivered in
  June 2026 recognized in January 2027 under ASC606 and June 2026 under IFRS15. Both renewal
  kinds pass; June's -900 difference is quantified as LICENCE_RENEWALS with zero OTHER residual.
- Advance consideration FX is verified with real monetary-vs-historical liability layers:
  EUR 1,000 remains EUR 1,000 in both books, while USD functional liability is 1,120 vs 1,100.
  The USD 20 effect is attributed to ADVANCE_CONSIDERATION_FX and transaction-currency effects
  remain zero. The helper now supports reusable real computation inputs for these scenarios.
- Necessary checks: seven focused real replay cases plus 34 relevant modification/licence
  regression cases passed; scoped lint/types and diff checks passed. Existing stored outputs
  remain unchanged; computations made before the correction may fail exact-original replay
  and retain the explicit fallback rather than fabricate provenance. No deployment.
- Remaining: book-context/non-policy residual cases and source gaps, Adoption Bridge currency
  support, Intercompany Pairs retained replay, other documented adapters and final repository
  validation. These verified renewal and historical-layer scenarios are no longer outstanding.

## Book Bridge verified phased attribution — October 21, 2026

- Added an authorized worker read/compute/publish path: verify original retained computation
  outputs and both book monetary endpoints, then run counterfactual ASC606 policy families in
  driver order using IFRS15 resolved values. Engine calls run outside SQL and heartbeat between
  evaluations. Publication rechecks complete-group read permission; ordinary narrow report
  scope does not gain access to a broader computation. Migration 0296 describes this basis.
- The collectibility phase also exchanges book-scoped Step 1 assessments/criteria events and
  reviewed collectibility/not-a-contract outcomes in memory. This is necessary because those
  recorded facts can differ even when policy replacement alone leaves revenue unchanged.
  Original event records are never edited. Input/output hashes and policy/event references
  accompany the retained per-contract driver effects.
- Multiple quantified causes now appear separately, including offsetting effects with a zero
  net difference. Later phases receive interactions. Proven nonzero effects remain visible
  beside OTHER; unsupported counterfactual phases leave the unproven remainder in OTHER.
  Older retained inputs and groups without verified common endpoints retain existing semantics.
- Necessary checks passed: real engine shipping election attributes USD 50 to FRAMEWORK_ELECTIONS;
  the public collectibility bridge performs actual replay and retains its expected -3,000 result;
  foreign functional/reporting views and same-source rerun after later billing pass; mismatched
  originals/endpoints get no causal labels, unavailable phases preserve the residual, offsetting
  causes remain visible; 29 focused tests, catalogue parity and scoped lint/types pass.
- Remaining: dedicated licence-renewal and advance-consideration FX scenarios and any resulting
  gaps, non-policy/book-context residuals, Adoption Bridge multi-currency, Intercompany Pairs
  retained replay, other documented adapters and final repository verification. No deployment;
  this is a concrete attribution increment, not a claim that every book difference is explained.

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
