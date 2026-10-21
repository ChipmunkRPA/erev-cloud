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
