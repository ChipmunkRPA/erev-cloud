# ENG-S14R10-FX-SIGN-1 — a role delta whose transaction and functional amounts differ in sign: design note

| Field | Value |
|---|---|
| Status | **Proposal for the supervisor's ruling. No engine change has been made for this item.** |
| Lane | ENG-FX (package `.run/sup2/lanes/ENG-FX.md`, Part 2), branch `sprint/l19`. Code references are to the head that carries this note, which includes the Part 1 commits `72803a90` and `38e4e010` |
| Written | 2026-09-30 (the file is named for the package date) |
| Witness | `backend/tests/engine/s14_posting/test_s14_fx_sign_witness.py`, committed with this note: eleven passing tests, five of which state today's refusal |
| Sources read | ENGINE_SPEC_B §12.2.2, S12-R-04 to S12-R-06, S14-R-04, S14-R-06, S14-R-10, S14-R-12, S14-R-15, S14-R-18, S14-R-27, S14-R-28, §14.2.4, §14.4, §14.6; POLICIES ALG-08 §2.9.1, ALG-09, POL-004, POL-161, POL-162, POL-181; 04 T-SL-04, T-SL-09, DB-06, DB-16; D-88 L7-6-Q-1; `docs/reviews/loop/sprint/L2-5.md` Q-34; `docs/reviews/loop/sprint/T1.md` (FX-DOMAIN); the BUILD_SPEC PRP-7 note; `backend/tests/unit/test_prp7_open_items.py`; the reviewer's note `PRODUCTION-S14-FX-SIGN-fd585009.md`; the code cited below |
| Evidence | **Measured**: run in this worktree — by the committed witness, or by an uncommitted scratch prototype where that is said. **Read**: established from the cited source. **Reasoned**: neither, and marked where it matters |
| Paths | `s12_fx_entities/`, `s13_books/`, `s14_posting/` and `s15_disclosures/` are under `backend/erev_engine/stages/`; `contracts/`, `journals/`, `close/` and `reports/` are under `backend/erev_api/domain/` |

## 1. Recommendation in short

Adopt **candidate B**. When the two amounts of a role delta differ in sign, post the delta as two lines of the same role in the same entry: a *transaction line* (the transaction amount, functional amount 0) and a *functional line* (the functional amount, transaction amount 0), each on the side of its own amount. Every other delta keeps its single line.

1. **It states nothing the engine did not compute.** The two lines carry exactly the two signed totals of the delta. No rate is chosen, no amount derived, nothing rounded. Candidate A must derive a division of the functional amount and adopt a rule for the rate that produces it.
2. **It continues what the ledger already does.** A line today carries the two net deltas of its role whatever rates lie behind them. The neighbouring case of the witness posts USD 2,000.00 / GBP 620.00 on one line (measured), which is no conversion of 2,000.00 at any one rate. B treats the opposed case the same way; A would decompose at a rate only where the signs happen to differ.
3. **Both line shapes exist.** Functional-only lines are common: every JET-10 line, and every re-layering of posted revenue without a transaction movement (measured in the witness and in the Part 1 database witness). A line with a nil functional amount is already admitted (`s14_posting/intents.py:153`). 04 T-SL-04 provides for rows with one amount at zero (`ck_subledger_line__amounts`; the generated `dr_cr`).
4. **No reported figure depends on the choice.** Journal summarisation nets the lines of a role per account in each currency independently (S14-R-18), so journal lines, the CSV file, every answer key and every golden are the same under A and B. The choice is how the subledger of record reads.

Candidate A is a defensible alternative if the accountant wants every transaction-bearing subledger line to show a functional amount at a stated rate; §5 gives its cost. Candidate C (keep refusing) is not tenable: §2 shows that an ordinary month reaches the refusal, and that the refusal turns on when computations run and not on the facts.

No schema change is needed for A or B. Alembic 0082 stays unused.

## 2. The defect

### 2.1 Mechanism (read)

| Step | Source | What happens |
|---|---|---|
| 1 | `s13_books/__init__.py:1807` (`_control_flows`, `:1726`); ENGINE_SPEC_B §12.2.2 "period-end flows" | The revenue of a period relieves the control role in one flow per obligation, dated the period end |
| 2 | `s12_fx_entities/__init__.py:318` `_measure`, `:346` | Stage 12 replays the flows in date order, so an invoice dated inside a period is processed before that period's revenue |
| 3 | `s12_fx_entities/layers.py:390` `credit` | The invoice settles open asset layers; the rest creates a liability layer at spot on its layer date (S12-R-04) |
| 4 | `layers.py:501` `debit`, `:621` `relieve`, `:566` `debit_rate` | Revenue relieves open liability layers at their historical functional amount (S12-R-05); the remainder becomes an asset layer at the POL-162 rate (S12-R-06) |
| 5 | `s14_posting/targets.py:610` `_relief`, `:642` | The revenue part takes its transaction target from stages 09 and 10 and, separately, its functional target from stage 12 |
| 6 | `s14_posting/assign.py:512` | `amount = (now_txn − before_txn − posted_txn, now_fn − before_fn − posted_fn)`: two independent deltas (S14-R-04). A closed origin is redirected unchanged (S14-R-06; `:523`) |
| 7 | `s14_posting/intents.py:272` | The entry is checked to balance in both currencies (S14-INV-01). It does |
| 8 | `s14_posting/intents.py:153` `_side`, called at `:283` | `IntentLine` has one `side` for two non-negative amounts (`backend/erev_engine/bundle.py:750`), so opposed signs raise `ENGINE_INVARIANT_VIOLATED`, labelled `S14-R-10` |

The S14-R-10 row states no sign rule. The refusal is the engineering decision L2-5-Q-34 (`L2-5.md:261`), which took opposed signs for an effect of "rounding at different rates". The cause is not rounding: it is the re-layering of revenue already posted (steps 3 and 4) netted against new revenue of the same period.

### 2.2 Condition

Let R be revenue already posted for a period at the period rate a (unbilled: an asset layer). An invoice of B ≤ R dated in that period, with spot s on its layer date, becomes known together with further revenue δ of the period. Then Δtxn = δ and Δfunctional = B·(s − a) + δ·a. For δ > 0 the signs differ whenever **B·(a − s) > δ·a**: a small further quantity against a larger invoice whose spot is below the period rate (for δ < 0, a spot above it). At s = 0.8000 and a = 0.8100 it is enough that δ is less than 1.23 % of B.

### 2.3 Reach (measured by the witness)

1. **No lock and no late event are needed.** The two strict expected failures of `test_prp7_open_items.py` reach the refusal through a locked period. The witness's first form is one open month: deliver, compute, invoice, deliver one more unit, compute. The T1 record classed the exposure as "reachable through ordinary late events"; it is wider than that.
2. **The invoice may be dated before the delivery or after it.** Because of step 1 above, an invoice dated before the last day of the month is layered before the month's revenue. The witness runs with the invoice on 5 January and on 20 January (the delivery is on 10 January) and gives the same figures.
3. **The refusal turns on when computations run.** Computed after each event, the same history is accepted: the invoice alone posts Dr REVENUE / Cr CONTRACT_LIABILITY GBP 1,000.00 with no transaction amount, the last unit then posts Dr CONTRACT_LIABILITY / Cr REVENUE USD 1,000.00 / GBP 810.00, and the posted totals are those of the target. Computed once after both events, it is refused. The opposed delta is the sum of two entries the ledger already takes.
4. **It turns on the size of the last delivery.** With a line of 102 units, two further units give +2,000.00 USD / +620.00 GBP and post on one line; one further unit is refused.
5. **No bound on rates excludes it.** The witness uses spot 0.8000 and average 0.8100. The second option of the PRP-7 note — to refuse such rate sets as malformed input — is therefore not available.

### 2.4 Consequence (reasoned, except the last sentence)

While the delta stands, every computation of the combination group raises, because targets are cumulative and the delta is measured again each time. Nothing of the group posts: its other obligations, reclass and remeasurement included. The platform has no action that resolves it. It ends only if a later event happens to bring the two amounts to one sign (measured: item 4 above).

## 3. The witness

`backend/tests/engine/s14_posting/test_s14_fx_sign_witness.py`. It is the case of the second pin (`test_eng_s14r10_fx_sign_1_codex_1508_arithmetic_inside_the_rate_bound`: one point-in-time line, a delivery that is computed, then an invoice and one more unit), with market-like rates in place of spot 1 / average 2, with a first form that needs no lock, and with the invoice dated on either side of the delivery. It runs through the same in-memory platform as the pins (`support.platform_props`, `erev_engine.compute`).

**World.** Entity functional currency GBP; contract `K-1` in USD; one point-in-time line `POB-01`, 101 units at USD 1,000.00 (SSP 1,000.00). Policies at their defaults: `fx.unbilled_revenue_rate` = `PERIOD_AVERAGE` (POL-162), `fx.cl_layer_consumption` = `FIFO` (POL-161), `billing.posting` = `ERP` (POL-004).

| Rate pin (USD → GBP) | Key | Value |
|---|---|---|
| Spot, 1 January 2026 (the latest on or before either invoice date) | `USDGBP-SPOT-2026-01-01` | 0.8000 |
| Average, FY2026-P01 | `USDGBP-AVERAGE-FY2026-P01` | 0.8100 |
| Closing, FY2026-P01 | `USDGBP-CLOSING-FY2026-P01` | 0.8200 |

**Events and amounts (all measured).**

| # | Event | Stage 12 | Cumulative January target, CONTRACT_LIABILITY (REVENUE is the mirror) |
|---|---|---|---|
| 1 | `CONTRACT_BOOKED`, `CONTRACT_ACTIVATED`, 1 January | — | — |
| 2 | `DELIVERY_RECORDED`, 10 January, 100 units | asset layer 100,000.00 at the average: 81,000.00 | +100,000.00 USD / +81,000.00 GBP |
| — | computation: **posted** Dr CONTRACT_LIABILITY / Cr REVENUE | | posted +100,000.00 / +81,000.00; rate reference `USDGBP-AVERAGE-FY2026-P01` |
| 3 | `BILLING_RECORDED`, USD 100,000.00, dated 5 January or 20 January | liability layer at spot: 80,000.00 | |
| 4 | `DELIVERY_RECORDED`, 21 January, 1 unit | January relief 101,000.00 at the period end: 100,000.00 from the layer at its historical 80,000.00, then an asset layer 1,000.00 at the average: 810.00 | **+101,000.00 USD / +80,810.00 GBP**; references average and spot |
| — | **delta = target − posted** | | **+1,000.00 USD / −190.00 GBP** (REVENUE: −1,000.00 / +190.00) |

The −190.00 is −1,000.00 (100,000.00 of revenue moves from 0.8100 to the invoice's historical 0.8000) plus 810.00 (the new unit). Entry totals: transaction +1,000.00 − 1,000.00 = 0; functional −190.00 + 190.00 = 0.

| Test | Asserts |
|---|---|
| `test_the_first_delivery_posts_100_000_at_the_january_average` | the amounts posted before and their rate reference |
| `test_the_revised_january_target_is_101_000_at_80_810` (both invoice dates) | the upstream target and the three layer movements, by computing the revised history with nothing posted |
| `test_eng_s14r10_fx_sign_1_one_open_month_is_refused_today` (both dates) | form **W1**, January open throughout: `ENGINE_INVARIANT_VIOLATED`; detail `amount_txn` 100000, `amount_functional` −19000, entry kind `REVENUE_RECOGNITION`, posting period FY2026-P01 |
| `test_eng_s14r10_fx_sign_1_after_the_january_lock_is_refused_today` (both dates) | form **W2**, January closed with its lines sealed first: the same delta redirected to FY2026-P02 with origin FY2026-P01 |
| `test_the_same_history_computed_after_each_event_posts_without_refusal` (both dates) | §2.3 item 3 |
| `test_two_further_units_instead_of_one_post_one_net_line` | §2.3 item 4: the line of 102 units with two further units |
| `test_eng_s14r10_fx_sign_1_one_further_unit_of_the_longer_line_is_refused_today` | §2.3 item 4: the same line with one further unit |

The five tests named `…_refused_today` state the decision as it stands and are rewritten under the ruling; the others hold before and after. The two existing pins are untouched.

## 4. The candidates with the witness's numbers

Every line below: book ASC606, entity `US01`, entry kind `REVENUE_RECOGNITION`, class `EVENT`, subject `K-1/POB-01`, accounts of the test chart (CONTRACT_LIABILITY 2400, REVENUE 4000). Period column: **W1** posts in FY2026-P01 with no origin and no reason; **W2** posts in FY2026-P02 with origin FY2026-P01 and reason `LATE_EVENT`. "K10" is the ten-member line-key object of S14-R-15 for the delta, unchanged; "K10 + leg" adds one member (§6). "Stamp" is the one rate the platform stores on the row: of the line's references, the one with the latest effective date (D-88 L7-6-Q-1) — here the January average.

### A — a transaction line at the governed rate, and a functional residual line

"The governed rate" has to be defined. Taken as the line's own stamp (0.8100): functional amount of the transaction line = round(1,000.00 × 0.8100) = 810.00; residual = −190.00 − 810.00 = −1,000.00.

| Line | Role | Account | Period | Transaction (USD) | Functional (GBP) | Side | Stamp | Key |
|---|---|---|---|---|---|---|---|---|
| A1 | CONTRACT_LIABILITY | 2400 | W1 P01 / W2 P02 | 1,000.00 | 810.00 | D | average 0.8100 | K10 |
| A2 | CONTRACT_LIABILITY | 2400 | same | 0.00 | 1,000.00 | C | average 0.8100 | K10 + leg |
| A3 | REVENUE | 4000 | same | 1,000.00 | 810.00 | C | average 0.8100 | K10 |
| A4 | REVENUE | 4000 | same | 0.00 | 1,000.00 | D | average 0.8100 | K10 + leg |

Role totals: CONTRACT_LIABILITY +1,000.00 USD; +810.00 − 1,000.00 = −190.00 GBP. In role, side and amounts these four lines are the ones the two-computation path of §2.3 item 3 posts. That agreement holds where the stamp is the rate at which the new transaction amount was measured. The stamp is a rule of effective dates, so it fails, for example, when the new amount relieves an earlier liability layer at its spot while the role's latest reference is a period average (reasoned). The lines above are computed by hand and not prototyped: stage 14 holds no rate values today.

### B — a transaction line and a functional line

| Line | Role | Account | Period | Transaction (USD) | Functional (GBP) | Side | Stamp | Key |
|---|---|---|---|---|---|---|---|---|
| B1 | CONTRACT_LIABILITY | 2400 | W1 P01 / W2 P02 | 1,000.00 | 0.00 | D | average 0.8100 | K10 |
| B2 | CONTRACT_LIABILITY | 2400 | same | 0.00 | 190.00 | C | average 0.8100 | K10 + leg |
| B3 | REVENUE | 4000 | same | 1,000.00 | 0.00 | C | average 0.8100 | K10 |
| B4 | REVENUE | 4000 | same | 0.00 | 190.00 | D | average 0.8100 | K10 + leg |

Measured with a scratch prototype (a test-session patch that divides an opposed delta into two before `group_into_entries` and adds the key member; not committed), for both invoice dates:

- exactly these four lines in W1 and in W2, all four naming the references average and spot; entry sums 0 / 0;
- posted totals after the entry equal the target (10,100,000 / 8,081,000 minor units), and the same events computed over these postings emit no intent — also in W2, where the read-back then holds a posted amount with opposed signs (+1,000.00 USD / −190.00 GBP, posting period FY2026-P02, origin FY2026-P01);
- in W2 the close-run passes that follow compute: 960.00 of the January remeasurement of 1,000.00 is taken back (Dr FX_GAIN_LOSS / Cr CONTRACT_LIABILITY), February's reclass is 1,000.00 / 850.00, and the posted January reclass of 100,000.00 / 82,000.00 is reversed at its posted rate;
- both existing pins compute;
- the stage 12 and stage 14 engine suites with the pins module under the prototype: 247 passed, 1 expected failure, 7 failed — the two pins (passing, which `strict` reports as a failure) and the witness's five refusal tests, and nothing else. An earlier run of the whole engine and unit suites, before the witness took its final form, gave 4,094 passed with the same two pins and the then two refusal tests failed (and 10 errors in the six database-bound unit modules, which collided with another database run of the lane and do not reach the engine); the property suite passed (39).

### C — keep refusing

No line: `ENGINE_INVARIANT_VIOLATED` while the delta stands (§2.4). If this is ruled, the limitation should be written into S14-R-10 and the release notes in plain terms — a foreign-currency contract cannot be computed when an invoice of a period becomes known after revenue of that period was posted and the period's further revenue is small against it — and the invariant label should stop citing S14-R-10, which holds no such rule. The refusal would remain dependent on the timing of computations (§2.3 item 3).

### Considered and set aside

| Candidate | Lines for the witness | Why not |
|---|---|---|
| D — one line with independently signed amounts | CONTRACT_LIABILITY +1,000.00 USD / −190.00 GBP on one row; the database admits it and the generated `dr_cr` would be `C` | `IntentLine` and every reader that pairs one side with both amounts would have to change: the engine's own entry check (`backend/erev_engine/__init__.py:1558`), persistence (`contracts/computation.py:918`), the stage 15 disclosures that read the transaction amount by side (`s15_disclosures/waterfall.py:121`, `disaggregation.py:66`, `rollforward.py:288`), and on the platform `reports/builders/balance_aging.py:308-317` and `reports/builders/contract_cost_rollforward.py:135`, which take the direction of `amount_txn` from `dr_cr` — for this row, from the sign of the other currency |
| E — reverse what was posted and post the target again (the reviewer's "source-signed component legs before netting") | per role Cr 100,000.00 / 81,000.00 and Dr 101,000.00 / 80,810.00 | ALG-09 step 4 and S14-R-04 post the delta, not a reversal and a re-post. It passes 201,000.00 through the period for a movement of 1,000.00, in W2 as `LATE_EVENT` lines of origin January. It offers nothing if the period movement of a target is itself opposed (not examined) |
| F — take the functional difference to `FX_GAIN_LOSS` | — | Excluded by the package: it changes the role totals and manufactures a gain or loss |

## 5. What each candidate does

| Dimension | A | B | C |
|---|---|---|---|
| Entry balance in both currencies (S14-R-10, S14-INV-01; seal trigger DB-06 (2); the engine's entry check) | Holds: each role's two lines sum to its delta, and the deltas balance | Holds (measured) | Not reached |
| Role totals per period, origin and currency; S14-INV-04, S14-INV-06 | Preserved exactly | Preserved exactly (measured) | Nothing posts |
| Contract balances (T-CON-09) | Unaffected: balances are computed from targets (S10-R-09) | Same | Frozen at the last computation |
| FX gain or loss | None arises | None arises | — |
| Amounts not computed upstream | Two per opposed role (810.00 and 1,000.00), from a rate convention | None | — |
| Line key and identity (S14-R-15) | The second line needs a discriminating member; the first keeps K10, so the EX-14-A vector stands. Precedent: the `reason_code` member of a reason-variant line (S14-R-27) | Same | — |
| Idempotent re-posting (S14-INV-02, RCP-21) | The RCP-05 read-back sums both lines into the role grain (they carry one stamp), so a recompute measures 0 (reasoned: the sums are those of B) | Same (measured: no intent in W1 and W2) | — |
| Replay determinism | A function of the delta, the stamp rule and a rate value; the lines change if the stamp rule changes (D-88 makes one stamp per line a rule for the release candidate) | A function of the delta alone | — |
| Later deltas of the same role | Needs a rate value each time. A delta under S14-R-28 (b) names references that the bundle may not pin; whether such a delta can be opposed was not established, and A would need a rule for it | Always two lines, whatever was posted before (measured in W2) | — |
| Rate references and stamp (S14-R-28, S14-INV-08, REQ-FX-006) | Both lines name the delta's references. A1 satisfies functional = transaction × stamp | Both lines name the delta's references. B1's stamp does not describe its functional amount (0), as the stamp of a multi-rate line does not today | — |
| Calculation trace (§14.6) | Both lines cite the role's `posting_target` node; the added line has its own `account_resolution` node. The converted amount and the residual are new figures and need a formula and a node each to stay re-evaluable (DG-ENG-04) | Both lines cite the role's `posting_target` node; the added line has its own `account_resolution` node. No new figure | — |
| Engine surface | The pinned rates bound to stage 14 (today the book loop binds them to stage 12 only), the stamp rule repeated in the engine, two formulas | A branch in `group_into_entries` and one line-key member | None |
| Seal control totals (gross debits and credits per currency) | Functional turnover 1,810.00 each way for a net of 190.00 | 190.00 each way | — |
| Journal summarisation (S14-R-18; `journals/summarise.py:146`, `:310`) | Identical under A and B: a role's lines share the grouping key (currency, account, dimension set, counterparty, origin period) and net per currency independently. W2: origin January is its own group, so the journal line of account 2400 has `debit_txn` 1,000.00 and `credit_functional` 190.00, and account 4000 the mirror. T-SL-09's two CHECKs allow it and the batch balances in both amounts (DB-16). W1: the same line when a run covers the second posting alone, the ordinary 101,000.00 / 80,810.00 when it covers both (reasoned from the rule and from the measured nets per account) | Same | — |
| CSV export (REQ-JE-011; `journals/export.py:122`, `:272`) | Identical under A and B: the file has transaction debit and credit only — 2400 debit 1,000.00, 4000 credit 1,000.00. No functional amount is in the file (read) | Same | — |
| NetSuite and QuickBooks adapters | Nothing to run: `NetSuiteGl.post_chunk` refuses by design (CLO-13; `backend/erev_api/adapters/gl/netsuite.py:167`), the NetSuite mock does not mock journal posting, and there is no QuickBooks adapter (the E-37 literal only). The port's `ChunkLine` carries four independent amounts (`journals/ports.py:72`) | Same | — |
| Can a general ledger hold the line? | What reaches a ledger is the journal line, which is the same under A and B. Of the subledger lines, A1 to A4 each have a ledger shape (a foreign line at a rate; a base-currency-only line) | The same journal line. Of the subledger lines, B1 alone (a foreign amount with no base amount) has no ledger shape | — |
| FX remeasurement of later periods | Unaffected: layers are rebuilt from events, and posted lines are not an input of stage 12. JET-10 deltas have no transaction amount and are never opposed | Same (measured in W2) | — |
| Reports that read `amount_functional` by side | `close/queries.py:321` `journal_preview`: for the entry, CONTRACT_LIABILITY debit 810.00 / credit 1,000.00 | The same report: debit 0.00 / credit 190.00. Both balance | — |
| Readers of `amount_txn` by side or sign (stage 15 disclosures; aging; cost rollforward; out-of-period register) | Signed transaction sums unchanged: a transaction-bearing row has the side of its transaction amount and the functional row contributes 0. The register's `line_count` rises by one per opposed role | Same | — |
| Screens | The subledger drill shows each row's side and both amounts (`frontend/src/routes/journals/run-lines.tsx:606`); both rows read correctly (read) | Same | — |
| Answer keys, goldens, parity | **None changes.** The two-line form replaces only the raise, so an input that computes today computes to the same output; every key and golden computes today | Same; measured under the prototype as in §4 | None |
| The stateful machine's rate bound (PRP-7 restriction (i)) | Can be lifted once lines exist | Same | Stays |

**On the general ledger.** The question does not separate the candidates. A journal line with a debit in the transaction currency and a credit in the functional currency, and journal lines with functional amounts only (every remeasurement), exist whichever is ruled. A ledger that derives base amounts from one exchange rate per journal — the usual design, stated from general knowledge and not checked against the NetSuite or QuickBooks Online interfaces — can take neither inside a foreign-currency journal; both need a base-currency adjusting entry, which is work for the export adapters (CLO-13). The CSV file cannot express either today, because it has no functional columns (§9).

## 6. Candidate B: amendments, code and tests

**ENGINE_SPEC_B** (revision 1.50 is Part 1's; the next number the supervisor assigns).

- S14-R-10, appended: "**Opposed signs.** The transaction delta and the functional delta of a role key are derived independently (S14-R-04), so with every rate positive they can still differ in sign — for example when an invoice becomes known after revenue of its period was posted at the period rate. Such a delta posts as two lines of the same role in its entry: a *transaction line* carrying the transaction amount with a functional amount of 0, and a *functional line* carrying the functional amount with a transaction amount of 0; each takes its side from its own amount. A delta whose amounts agree in sign, or one of whose amounts is 0, posts one line. The two signed totals of the role per posting period, origin period and currency are those of the delta; the entry balances in each currency (S14-INV-01); the split uses no rate and creates no `FX_GAIN_LOSS` line."
- §14.2.4 pseudocode: `group_into_entries` expands each delta into its lines before sorting — one line, or the two of S14-R-10 — and the sort key and `resolve_account` take the side from the line's own non-zero amount (`signed_txn or signed_functional`). As written the pseudocode reads `signed_txn` alone (§9).
- S14-R-12, appended: "An entry holds one line per role delta, or the two lines of S14-R-10. Lines are ordered debit first, then by role, clearing purpose and counterparty (§14.2.4); the two lines of one role differ in side, so the order stays total."
- S14-R-15, appended: "The functional line of an opposed delta (S14-R-10) adds the member `currency_leg` = `FUNCTIONAL` to the line-key object; its transaction line and every other line keep the object above, so the EX-14-A vector stands."
- S14-R-28, appended: "Both lines of an opposed delta (S14-R-10) name the delta's references."
- §14.4, new S14-INV-09: "The non-zero amounts of an intent line share one side. A role delta whose amounts differ in sign is two lines (S14-R-10)."
- §14.6, appended to the closing paragraph: "Both lines of an opposed delta carry the `posting_target` node of their role, and each has its own `account_resolution` node."
- The ruling records L2-5-Q-34 as amended: its side rule stands for each line, its refusal is withdrawn.

**04-DATA_MODEL T-SL-04** (revision 1.102 is taken by ruling R-11 of this lane; a number from the supervisor), `amount_functional` note, appended: "One role's movement in an entry is stored as two rows — a transaction row with `amount_functional = 0` and a functional row with `amount_txn = 0` — when its two amounts differ in sign (ENGINE_SPEC_B S14-R-10)." No column, constraint or migration changes.

**BUILD_SPEC PRP-7** (fragment `12-engine.md`; header `00-header.md`): the coverage-restriction note — restriction (i) and the ENG-S14R10-FX-SIGN-1 paragraph — restated as ruled; the two pins become witnesses.

**Code.** `s14_posting/intents.py`: `group_into_entries` emits the two lines where `_side` raises today, and `line_key` takes the leg. Nothing else in the engine. Nothing on the platform (read: `ck_subledger_line__amounts` admits both rows; the seal trigger balances each currency per entry; `_post_book` signs each line by its own side and stamps both from the same references). `ENGINE_VERSION`: an input that failed now computes — a minor step under DG-ENG-10, folded into the one owed 0.3.0 → 0.4.0.

**Tests.**

1. The witness module: the five refusal tests rewritten to assert, for W1 and W2 and both invoice dates, the four lines, the entry sums, the role totals, the references on all four lines, distinct and stable line keys (a vector for the functional line), and that a recompute over the postings emits nothing.
2. The two pins of `test_prp7_open_items.py` turned from strict expected failures into passing witnesses of their own figures (the second: JPY +10 / USD −30.00; the first: −5,518,692 / +361,485,316 in minor units of JPY and CLF).
3. `test_s14_entries.py`: an entry of three roles (the agent split of EX-14-A in a foreign currency) in which some deltas are opposed and others are not; and a reason-variant line (S14-R-27) with opposed amounts, whose functional line carries both added members.
4. A database witness on the public events route (deliver, compute, invoice, deliver): the computation succeeds; four rows are stored with the expected `dr_cr` and the same rate stamp; the seal balances; the read-back equals the target and the next computation posts nothing; a journal run over both postings has one ordinary line per account, and a run over the second posting alone has the line with `debit_txn` and `credit_functional`; the CSV rows are as §5 states.
5. The property suite under the `ci` profile with the machine's rate bound lifted as far as ruled. P5 (balance per currency) and P9 (idempotency) already cover the lines.

## 7. What an accountant should confirm

1. **Presentation.** That the subledger of record may show this movement as a transaction-currency line without a functional amount and a functional-currency line without a transaction amount (B); or that a transaction-bearing line should show a functional amount at a stated rate (A) — and then which rate: the row's stamp, or the POL-162 rate of the origin period. No reported total differs. If A is preferred on principle, the same principle would apply to every delta that combines rates and agrees in sign, which posts on one line today (§2.3 item 4); that is a larger question than this item.
2. **The measurement is taken as given, and rests on two existing rules.** (a) The revenue of a period relieves the control role in one flow dated the period end (§2.1 step 1), so an invoice dated before the last day of the month is layered at spot before the month's revenue relieves it — also an invoice dated after the delivery, as on 20 January in the witness. (b) A computation posts the difference between the cumulative target and what is posted, in the role, with no gain or loss line (S14-R-04; for a closed period ALG-09 steps 4 and 5 and POL-181). Under (a) and (b) the functional revenue of January falls by GBP 190.00 in a computation in which its transaction revenue rises by USD 1,000.00. Neither rule is changed by A or B, and the engine posts such re-layering differences today whenever the two amounts agree in sign (§2.3 items 3 and 4).
3. **What is not proposed.** Were relief dated at the performance date instead, the 20 January invoice would settle an asset layer at spot (ALG-08 §2.9.1, first row): revenue GBP 81,810.00 and a settlement loss of 1,000.00, the same 80,810.00 in total, with a delta of +1,000.00 / +810.00. That is a measurement question outside this item. It would not remove the defect: the invoice dated 5 January, before the delivery, is an advance under either reading and gives the opposed delta (measured under the present rule; reasoned for the other).

No GAAP conclusion is offered here.

## 8. Questions for the ruling

1. A, B or C.
2. If A: the governed rate, and whether the pinned rates may be bound to stage 14.
3. The name of the line-key member (`currency_leg` = `FUNCTIONAL` proposed).
4. How far the stateful machine's rate bound is lifted (proposed: removed, with any new failure reported rather than bounded again).
5. Whether a corpus answer key for the witness is wanted; it changes the corpus counts.
6. Whether §7 item 3 is to be opened as its own item.

## 9. Noticed while reading; outside this item

- The CSV export has no functional columns, so a journal line with functional amounts only (every FX remeasurement) exports as 0.00 / 0.00 (`journals/export.py:122`). Read, not run.
- The §14.2.4 pseudocode takes the side and the line order from `signed_txn` alone; the code takes the functional sign when the transaction amount is nil (`s14_posting/intents.py:153`). By the pseudocode every functional-only line would be a credit.
- For a role outside `FX_REMEASUREMENT`, the functional amount of a line is not the value of any trace node: `posting_delta` carries the transaction delta, the cumulative functional amount is a parameter of `posting_target`, and the posted functional total is not in the trace (`s14_posting/assign.py:685`). True today of every foreign-currency line; unchanged by A or B.
- `reports/builders/balance_aging.py:308-317` multiplies the signed `amount_txn` by a sign taken from `dr_cr`, so a credit and a debit to CONTRACT_LIABILITY both give a negative flow. Read, not run; not verified as a defect.
- The journal line drawer takes its side and amount from the transaction columns (`frontend/src/routes/journals/run-lines.tsx:778`), so a functional-only journal line is titled as a credit of 0.00. Read, not run.
