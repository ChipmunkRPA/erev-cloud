# CTR-ASOF-KPI-1 — contract figures at `as_of` (design note)

Lane QA-BE, item B-2, 2026-09-30. For the supervisor's ruling; nothing is built. Measured on the seeded Avenmoor tenant in the lane's dev database, branch `sprint/w2` at 39c207ee.

**1. Finding.** 04 API-C-10: "to-date measures include activity with `effective_date ≤ as_of`" (REQ-PLT-030, P0); 03 REQ-REC-021: "For every POB, book and `as_of`: allocated = recognized to date + scheduled + awaiting trigger." Built: every contract read returns the version's columns, which hold the value at the version's effective date d_v (ENGINE_SPEC CV-50, Table 0.9-A), whatever `as_of` is (`queries._kpis`, `_build`, `obligation_outs`). The header balances ignore `as_of` too: they are the stored `contract_version_balance` row, the balance of the version's latest period. So BG-AVM-0012 (daily ratable 10,800.00, d_v 2026-01-01) shows recognized 29.59, scheduled and RPO 10,770.41 beside contract asset 8,077.81.

**2. What a version stores (measured).**

| Store | Time elapsed (BG-AVM-0012) | Event-driven (SF-ORD-10001 O2, output percent; NS-SO-DE-5004 O1, units) |
|---|---|---|
| Version columns | at d_v: 29.59 | at d_v |
| Trace nodes `revenue_cum`, `progress_ratio` `:<obligation>:<period>` | every period of the term, future ones included (P09 8,077.81, P12 10,800.00) | every period from inception to the horizon (0.00 before the first event), none later |
| Trace nodes `billed_cum`, member balances | inception to the horizon (P01 to P09) | the same |
| `schedule_line` | one per period; `cumulative_amount` = the node | only where an amount exists; none while awaiting a trigger |
| Ledger REVENUE lines | P01 to P09 = 8,077.81 | the periods with an amount |
| `subledger_line.schedule_line_id` | never written by a computation's posting (0 of 9) | 0 of 2 |

`scheduled_amount`, `awaiting_trigger_amount`, `rpo_amount` have version-state nodes only. `calc_trace`: 1,308 rows; 93 / 236 / 549 nodes (minimum / median / maximum); 12.8 kB stored on average.

**3. Members.**

| To-date measures (move with `as_of`) | Version facts (do not move) |
|---|---|
| API-S-Contract `kpis.revenue_to_date`, `billed_to_date`, `scheduled`, `rpo`, `kpis.balances[]`, `kpis_ratios.billed`, `.recognized`, `steps[RECOGNITION].detail.recognized_ratio` — and so the SF-02 columns Recognized, Billed, RPO, Scheduled | `kpis.transaction_price`; `awaiting_trigger`, `pending_trigger_count` (an event moves them, and an event makes a version); `status_reason`; the other steps |
| API-S-Obligation `to_date.revenue`, `.billed`, `.progress_ratio`, `remaining.allocation`, `scheduled`, `ratios.recognized`, `.scheduled`, `position`, `satisfaction_status` (S09-R-46) | `original.*`, `current.*`, `ssp.*`, quantities, `to_date.catch_up*`, `remaining.quantity`, `.ssp`, `.billing`, `awaiting_trigger`, `netting_reclass` |
| API-S-ContractBalance; API-S-ScheduleLine `state` (6) | the version summaries, `/versions/{n}` and `/versions/compare` — the audit view of a computation, labelled by its own date; schedule amounts; the allocation walk |

With Δ = C(cut) − C(d_v) per obligation: revenue rises by Δ; `scheduled`, `remaining.allocation` and RPO fall by Δ; an obligation satisfied at the cut leaves RPO. This is the overlay the answer-key runner applies on the same nodes (`runners.py` `_CheckpointComparison.to_date`, L4-3-Q-10). SF-02 sorts and filters on no to-date measure (SCREENS §3.5; sort keys `contract_no`, `inception_date`, `transaction_price`, `updated_at`).

**4. The cut — recommended: the end of the period containing `as_of`, not later than the version's horizon.** The engine evaluates period-end targets only (05 RCP-03); ledger reads cut at the period end (API-C-10); report balances read the period nodes (`tie_outs.balances_at`, R-16); the UI always sends a period end (PRD BR-UX-02). An exact-date cut needs an engine run per read and would disagree with the balances beside it. The cap: a time-based obligation has nodes to the end of its term, so without it a later `as_of` reports the schedule as recognized.

**5. The source — recommended: the version's trace period nodes, one reader for figures and balances.**

| Case | Trace period nodes | Posted ledger lines | Schedule lines |
|---|---|---|---|
| Event-driven obligation | a node per period to the horizon | right once posted | the sum of the lines to the cut: the same figure |
| Mid-period `as_of` after d_v | the period-end figure (4) | the same | the same |
| `as_of` before d_v | that period's node, by EFFECTIVE period; quantities and the allocation stay the version's — a look-back on amounts, not a replay (the replay is `known_at`) | by POSTING period: a late event sits in a later period (RCP-04), against API-C-10 | as the nodes |
| Ledger not caught up (the period turned, no computation since) | the figure at the version's horizon; the response names that period and the screen shows the stale state (SCR-ST-08, item B-3) | silently through the old horizon | the future lines must be capped |
| Draft, quarantined or held contract | the provisional version's targets | nothing | as the nodes |

Shown for BG-AVM-0012: at Sep 2026 recognized 8,077.81, scheduled and RPO 2,722.19, contract asset 8,077.81, schedule lines Jan to Sep recognized; at Jun 2026 5,355.62 with the June balance; at Dec 2026 the September figures, marked "measured at Sep 2026". Reader: `tie_outs.traced_balances` / `period_balances` extended to `revenue_cum`, `billed_cum`, `progress_ratio`, under the R-16 rule (a figure the trace cannot answer is refused by name, never replaced by the version column). No contract-level period node exists, so the contract cell is the sum of the obligation nodes less the JET-14 release (T-CON-08) and its Explain lists those nodes (SCREENS §4.1.4, docs first); no engine change.

**6. Schedule-line `state`.** 04 API-S-ScheduleLine: "`RECOGNIZED` when a subledger line exists for it as of `known_at`". Built on the link `subledger_line.schedule_line_id`, which no computation's posting writes, so every line reads SCHEDULED until a close run releases it. (a) Read the ledger line by contract, obligation, period and REVENUE role — recommended now; (b) stamp the link in `computation.persist` — with the close-release work (CLO-19 / 20), which needs it.

**7. Cost.** Pagination and sort are untouched (3). The header reads one trace, a single JSON document; a list page reads the traces of its rows in one `= ANY(:version_ids)` query (50 × 12.8 kB here). Should the workbench budget (05 PERF-02, p95 ≤ 300 ms) fail on large groups, `schedule_line` is the relational projection of the same nodes, behind the same function; not proposed now.

**8. Tests that move (none is a financial oracle).** `tests/domain/contracts/test_contract_reads.py:165` and `tests/api/test_obligations_api.py:138` (`state` "SCHEDULED" on an activated, computed contract: STALE EXPECTATION under 6); `tests/api/test_explain_api.py:558` (the Explain of `revenue_to_date` names the version-state node). `tests/api/test_contracts_api.py:555` names members only. Answer keys read versions and nodes, not these members.

**9. "Last computed" (finding Q-2).** SCREENS §4.1.2 binds the label to `context.known_at`, the read's record cut-off ("now"). Proposed: API-S-Context gains `computed_at` (the `created_at` of the computation that produced `contract_version_id`) and `measured_period` (`{period_key, end_date}`: where the to-date measures were measured, 4); SCREENS binds the label to `context.computed_at`.

**10. Rulings asked.** (1) the lists of 3; (2) the cut of 4, with 04 API-C-10 amended; (3) the source of 5, with the refusal by name and the draft row; (4) 6 (a) now, (b) later; (5) the two context members and the SCREENS binding; (6) numbers for 04 (API-C-10 and the five schemas), SCREENS (§4.1.2, §4.1.4) and the OpenAPI files. Size: one backend slice (the reader, five read functions, witnesses on a time-based, an event-driven and a consideration-payable contract) and one web slice with B-3 (meta row, stale marker).
