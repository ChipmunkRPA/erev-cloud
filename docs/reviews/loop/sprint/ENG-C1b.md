# ENG-C1b: the D-92 / D-93 rulings on the ENC-5 questions (lane C1b, sprint/l5)

Production-readiness programme, engine lane C1b (after ENG-C1, `ENC-5-input-measures.md`). Base
commit 3e6c99a (main after the ENG-C1 record merge and the C2a merge; fast-forwarded, clean tree).
Governing text: docs/01-DECISIONS.md D-92 (1), (1a), (2) and D-93 (1) to (4), with the spec-first
amendments already on main (ENGINE_SPEC rev 1.7 S06-R-11 series row, S06-R-15, S06-R-17, Table
0.4-A `CONSTRAINT` / `OTHER`; ENGINE_SPEC_B rev 1.9 S09-R-04 exception, S09-R-35 cause clause; 04
rev 1.12 T-CON-19, E-49 pending values, T-REF-30 note, §20 OQ-13; dev-guide rev 1.8 §9.5.3,
§9.5.4); the common dispatch terms (fail-first, `make lint`, parity alone, the 12:16 gate-slot
amendment and the 13:38 clarification, GATE-BIND-1); no ENGINE_VERSION bump in the lane (batch
bump at merge). AD-28 and AD-30 are open accountant judgments: the ruled rules are implemented and
the figures each yields are reported; no key edited beyond the rulings' own corrections and the
D-93 (4) basis annotations. Three Codex reviews of the lane's commits are answered in §3.

## 1. Commits on sprint/l5

| Commit | Scope |
|---|---|
| 8e96309 | D-92 (1)/(1a): same-date estimate versions recorded before the amendment belong to the modification (stage 01 pin index `applies_order_key`; stage 09 reader) |
| 4fe4bb1 | D-92 (2), D-93 (1), D-93 (2): answer-key corrections — inputs (FS-03-SEP contract, events and checkpoint cutoff; GE-08 event shape), ten added FS-03-SEP monetary assertions, two trace-selector changes (the CV-50 node names), REQ-MOD-011 / coverage annotations; the 150 pre-existing monetary checkpoints unchanged (Codex KEY-INPUT-DIFF) |
| 4778d5e | D-93 (3): the S04-R-04 claim gate and the S05-R-14 override accept the element code and the obligation subject |
| 77cc618 | D-93 (4): E-49 `PER_INCREMENT` / `PER_BOOKED_TERM` (enums, migration, OpenAPI, editor), `SspResolution.value_basis`, the S06-R-11 series branch, corpus annotations FS-03 A/B, CHK-043, K-02 factory |
| 6e64380 | Migration 0055 → 0056 (lane P2's sprint/l7 holds 0055; single-head coordination, §2.6) |
| f5d39d9 | Codex ENCODED-JUDGEMENT: the matcher compares the raw element code, never a split of the encoded key (§3.2) |
| e8a1e3c | Codex SERIES-BASIS S1 / S2: increments counted as the pinned convention counts the term; no reading inferred from the quantity (§3.3) |
| 0b5d2c6 | Codex SERIES-BASIS §3: undeclared series basis fails closed — 30 corpus entries annotated, loader refusal active (§3.4) |
| 299e36a | D-97 (3)/(3a) docs first: 04 rev 1.17 (E-131, T-REF-30 `quantity_unit`), ENGINE_SPEC rev 1.10 (S06-R-11 sentence), dev-guide rev 1.32 (§3.5) |
| 1434d07 | D-97 (3)/(3a): E-131 `quantity_unit` declared, never inferred (engine, migration 0056, API 422 rule, loader, fixtures) (§3.5) |
| fcc2b69 | D-97 (3) v3 docs: 04 row renumbered 1.17 → 1.19, ENGINE_SPEC 1.10 → 1.11; ρ-once wording; unit iff `PER_INCREMENT`; agreement scope; compatibility (§3.6) |
| 79b6742 | D-97 (3) v3 completion contract: unit iff `PER_INCREMENT` in every path, book-wide agreement at insert and at selection, CV-25 hash view, migration check fix (§3.6) |
| f3c1dc3 | D-97 (3) docs: 04 `value_basis` row one ρ-once expression; API-S-SspEntry conditional `AMOUNT` default and `quantity_unit` member (§3.6) |
| a815678 | D-97 (3) admission evidence: stored-versus-request control (same version, other key) as a DB test; synthetic-store unit tests (§3.6) |
| 8f0a5a2 | D-97 (3) admission: a contradictory retained stored population is refused before writing, naming every stored unit (§3.6) |
| 021a067 | SSP-ADMISSION-R1 docs: API-R-23 product read model carries the derived `requires_explicit_ssp_basis` (§3.8) |
| 053813f | SSP-ADMISSION-R1 (b): one series predicate — `products.series_product_ids` feeds the admission guard and `ProductOut.requires_explicit_ssp_basis` (§3.8) |
| (this record) | docs only |

## 2. Rulings and what was built

### 2.1 D-92 (1)/(1a): same-date estimate versions and the modification

Rule text read: S09-R-04 rev 1.9 exception ("an `ESTIMATE_CHANGED` version (`EAC` or
`VARIABLE_CONSIDERATION`) whose effective date equals the date d of a `CONTRACT_AMENDED` of the same
contract, recorded in the same date's batch with a lower `record_seq`, and whose estimate the
amendment's lines change or the class D / class N re-measurement of the modified obligation reads,
is the modification's updated estimate: it is not measured in the previous segment; the
pre-boundary state (C_before, the pool, the S06-R-11 weights) is measured without it and it applies
at the boundary"), S06-R-15 and S06-R-17 rev 1.7, S09-R-35 rev 1.9 ("produces no `CATCH_UP` or
`TP_CHANGE` cause of its own on d"), D-92 (1a) membership limits.

Design: stage 01 `pins.build(events, versions, contracts=…)` gives every `EstimatePin` the ENG-06
position at which its version applies (`applies_order_key`, default the applying event; the
applying event itself stays `event_order_key`, so `applied_version`, `decompose._estimate_version`
and the stage 08 late-event reader are unchanged). Membership (1a), stated in code
(`pins._member`): an `EAC` element naming an amended obligation (`obligation_key`, a target
obligation, or the unnamed element of a sole-obligation contract whose obligation is amended); a
`VARIABLE_CONSIDERATION` element with `allocation_target` `CONTRACT` (the pool re-allocates it,
S06-R-12 ΔVC) or `OBLIGATIONS` naming an amended obligation; never an `INCREMENTS` element
(realised amounts, S09-R-02); with several amendments on one date the first amendment after the
version in `record_seq`, never an earlier one; another date, another contract or an unrelated
estimate keep S09-R-04's ordering. `EstimatePins.pin(..., before)` and the stage 09 EAC reader
(`progress_inputs.eac_version`) compare that position, so stage 06's C_before, pool and weights are
measured without the version, its class N / class D measurement with it, stage 08's own event sees
a zero delta (no `TP_CHANGE` segment) and stage 09 raises no separate `CATCH_UP` / `TP_CHANGE` on d.

Fail-first (3e6c99a): `test_s06_same_date_versions.py`, 6 tests. The CHK-042 world with EAC v2
(75,000.00) recorded before the amendment gave pool 76,000.00, weights 70,000 : 30,000 (B progress
0.4) and shares 53,200.00 / 22,800.00; the pin index had no deferral and `build` no `contracts`
argument. After: pool 70,000.00, weights 62,500 : 30,000 (B progress 1/2), shares 47,297.30 /
22,702.70, B allocated 77,297.30, C′_B 30,918.92 (f = 0.4 post-change), catch-up 918.92, C
22,702.70 — the BUILD_SPEC `test_chk_042_mixed_d18_default` figures. The (1a) tests: an unrelated
same-date estimate applies at its own event; a CONTRACT-level VC defers and an `INCREMENTS` element
does not; two same-day amendments (v1 → the first, v2 → the second, v3 after both → its own event);
another date never defers.

Acceptance (five keys, no edit): MOD-CHK-027-S6-EX8, MOD-CHK-042-D18, MOD-CHK-042-INCEPTION,
MOD-CHK-115, MOD-S6-COMBINED-MOD-OWN — 5 selected, 5 passed on 8e96309. Codex
PRODUCTION-C1B-ORIGINAL-FIVE-8e96309: 5/5, 110/110 checks; the identical probe at e467e25 and at
the parent 3e6c99a gives 0/5, 94/110 with the same 16 mismatches (the change is isolated).

AD-28 figures (D18, reported, not decided): under the ruled rule contract `revenue_cum` 70,918.92
(L1-A 40,000.00 + L2-B 30,918.92), L2-B allocated 77,297.30 / L3-C 22,702.70,
`catch_up_modification_cum` 918.92 (weights 62,500 : 30,000, B progress 1/2 before the boundary,
0.4 from it) — equal to the key. Under the ENG-06-order reading (before 8e96309): 70,880.00,
77,200.00 / 22,800.00, `CATCH_UP` (6,000.00) then `MODIFICATION` 6,880.00.

### 2.2 D-92 (2): catch-up trace node names (key correction)

MOD-GE-02 and REC-BR-08 cite `catch_up@GE-02/EV-000005` (subject L1-WORK, −4,705.88) and
`catch_up@BR-08/EV-000008` (subject L1-TOOL, 2,941.18), the CV-50 nodes, instead of the retired
05 §3.6.8 name (D-76 OQ-A-23); values unchanged. REC-BR-08 passes; MOD-GE-02 proceeded to its
claim-gate mismatches (§2.4).

### 2.3 D-93 (1) and (2): key input corrections — no engine change

Both rulings are headed "(input clarification; no engine change)". D-93 (1): "A 606-10-25-12
separate contract is booked by the platform as a new contract in its own combination group … the
runner appends nothing for a SEPARATE_CONTRACT choice (L5-3-Q-18, now closed as built) … so the
key declares it"; the T-CON-01 `origin_modification_id` gap is 04 §20 OQ-13, not lane work. D-93
(2): "`CONTRACT_TERMINATED` PARTIAL selects whole obligations (S06-R-21) … Extending PARTIAL
termination to within-obligation units is NOT adopted." No automatic child-contract creation,
persisted lineage or within-obligation unit selection was built (the supervisor withdrew a relay
that read Codex's "not proved by the fixture review" as work owed).

What 4fe4bb1 changes, exactly (Codex PRODUCTION-C1B-KEY-INPUT-DIFF-4fe4bb1: 150 monetary
checkpoints retained; "follows D-92/D-93 but is NOT inputs-only"):

- MOD-FS-03-CASEA — inputs: contract FS-03-SEP (CUST-FS03, FS-US, inception 2026-07-01, L3-SEATS
  33,000.00 for 2026-07-01 to 2026-12-31; `CONTRACT_BOOKED`, `CONTRACT_ACTIVATED` and
  `BILLING_RECORDED` 33,000.00 on 1 Jul, seq 9–11); the July checkpoint's `after_seq` moves to 11.
  Added assertions (ten monetary): the FS-03-SEP block (TP 33,000.00; revenue_cum 5,500.00;
  billed_cum 33,000.00; L3-SEATS allocated 33,000.00, revenue_cum 5,500.00; contract liability
  27,500.00) and the contract-filtered subledger blocks FS-03 Cr 9,900.00 / FS-03-SEP Cr 5,500.00
  beside the entity-level 15,400.00 — the ruling's arithmetic authored as key values. MOD-FS03-A
  stays on FS-03 for the `SEPARATE_CONTRACT` proposal. The 5,500.00 is never injected into the
  parent's allocation (S06-R-03).
- MOD-GE-08 — input: the 31 Oct event re-keyed `CONTRACT_AMENDED` kind `QUANTITY_CHANGE`, payload
  `{modification: MOD-GE08-T4C}`, same terms line (5 units in force, 3 remaining after 2
  delivered; −600,000.00); name, narrative and every expected value unchanged. Passes with the
  engine unchanged (L1-PROTO 1,500,000.00 retained; L2-UNITS 900,000.00, quantity 5).
- MOD-GE-02, REC-BR-08 — trace selectors: `measure` renamed to the CV-50 node names of §2.2; the
  asserted values (−4,705.88; 2,941.18) unchanged.
- 03-REQUIREMENTS REQ-MOD-011 note and `_coverage/answer-keys-industries.md` GE-08 row note the
  event shape.
- Answer-key loader unit tests: 110 passed over the corrected keys.

### 2.4 D-93 (3): the claim gate and the POL-044 override

Rule text read: Table 0.4-A rev 1.7 `CONSTRAINT` / `OTHER` ("`estimate_key` (the element code of
the record's contract …; the engine also accepts the §0.4 qualified key …; the record may sit on the
contract or on the element's obligation — D-93 (3))"); S04-R-04; 04 T-CON-19 rev 1.12; dev-guide
§9.5.4 rev 1.8.

Design (4778d5e, corrected by f5d39d9 — §3.2): `judgement_names_subject(subject, contract,
obligation_keys)` and `judgement_names_element(outcome_key, estimate_key, element_code)` in stage 01
`convert`; `vc._claim_enforceable(ctx, st, contract_key, version)` and `targeted._overridden` read
them with the element's obligations (`obligation_key`, targets) and the element's own T-CON-12
`element_code`. The gate keeps its substance: another element, another contract, an obligation the
element does not name, another book or a false flag is refused.

Fail-first (8e96309): `test_s04_claim_gate.py`, 6 failed / 2 passed — the element code on the
contract and any record on the element's obligation left the 1,000.00 claim out (constrained
−300.00, TP 9,700.00 against 700.00 / 10,700.00); the POL-044 override with the element code or on
the target obligation did not clear `VC_TARGET_TOLERANCE_EXCEEDED` (EX-35 world: 35,556 / 244,444
after clearing). After: 8 passed; stages 01, 04, 05 suites 159 passed.

Acceptance: MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM passes (claim-attested TP 5,580,000.00,
constrained VC 280,000.00, revenue_cum 4,263,370.79; priced-and-settled TP 5,640,000.00). The
runner renders the stored obligation-scoped judgement verbatim, as production `bundles.py` does.

### 2.5 D-93 (4): the series SSP entry's pricing basis

Rule text read: S06-R-11 rev 1.7 series row ("class D series → the d SSP of the remaining
increments, priced from the SSP entry's declared basis (D-93 (4); 04 E-49 `ssp_value_basis`:
`PER_INCREMENT` × the remaining increments in [d, e_p]; `PER_BOOKED_TERM` ÷ the increments of the
term the entry prices × the remaining increments; an entry annotated as pricing the remaining
increments at d is taken as is; a series entry without a declared basis fails closed, CV-45, once
the corpus entries are annotated; increments are counted under the pinned E-21 convention as in the
D-90b paragraph below)"); 04 T-REF-30 rev 1.12 note; D-93 (4) ("FS-03B and K-02 as per-increment /
per-term; CHK-043 and EX-09-A as remaining-increment").

Design (77cc618, corrected by e8a1e3c and 0b5d2c6 — §3.3, §3.4): `SspValueBasis` gains
`PER_INCREMENT`, `PER_BOOKED_TERM` (erev_api, erev_engine; 04 E-49 rev 1.16; migration 0056
`add_enum_value` with `remove_enum_value` downgrade; OpenAPI regenerated; editor `VALUE_BASES` and
labels). `SspResolution.value_basis` records the entry's basis. `segments.series_basis_scale`
(stage 06): for an existing `series` obligation measured by `TIME_ELAPSED` with a `day` or `month`
increment whose entry declares a basis, ρ = 1 − f(d − 1) under the pinned convention over the term
in force (a whole period counts only once complete, so the current period counts as remaining —
D-90b); `PER_BOOKED_TERM` → value × ρ; `PER_INCREMENT` → value × increments × ρ, the increments
counted as the convention counts the term's periods (`progress.series_increments` /
`progress.time_units`: MONTHLY_EVEN whole periods plus day-prorated partial periods, MID_MONTH the
counted periods, DAILY the days; a month increment under DAILY takes the calendar-month weights)
and the line's quantity read as service units each spanning the term; `AMOUNT` → as today (the
remaining-increments reading); `unit` / `transaction` increments as today. `weights.existing`
(D18_DEFAULT) and `inception_basis.existing` (INCEPTION_ALL, from the inception entry's basis)
apply it; `mod.weights.d18.v1` and `mod.weights.inception_all.v1` keep their ids with the additive
params `series_basis`, `series_increment_unit`, `series_increments`,
`series_remaining_increments`, `series_multiplier` beside the D-90b single-layer params and
recompute the factor (`_series_multiplier`), so `reevaluate(trace)` stays exact.

Fail-first (4778d5e): `test_s06_series_basis.py` — stage 01 refused the literals (S01-R-11) and the
FS-03B-shaped world (12-month series subscription 120,000.00 with entry 132,000.00; added six-month
seats 26,400.00 with entry 33,000.00; amendment 1 Jul 2026, `MONTHLY_EVEN`) weighed 132,000 :
33,000 (4 : 1). After: `PER_BOOKED_TERM` 132,000 × 6 ÷ 12 = 66,000 and `PER_INCREMENT` 11,000 × 12
× 1/2 = 66,000 against 33,000 (2 : 1), shares 57,600.00 / 28,800.00 of the 86,400.00 pool
(the lane fixture has a 60,000.00 unrecognised balance; the key's own pool is 85,800.00 with shares
57,200.00 / 28,600.00 — Codex), params `series_increments` 12, `remaining_scale` 1/2,
`progress_as_of` 2026-06-30; `AMOUNT` stays 4 : 1 (69,120.00 / 17,280.00); the added obligation's
entry is never rescaled.

Annotations (input, no value change): MOD-FS-03-CASEA and -CASEB `SAAS-SEATS-12M` entries
`PER_BOOKED_TERM`; MOD-CHK-043-S6-EX7 `CLEAN-WK` entries `AMOUNT` (the remaining-increment
reading); the EX-09-A test fixture's `point_entry` already declares `AMOUNT`; the K-02 factory
seat-month range entry `PER_INCREMENT` (no platform test modifies K-02's series obligation, so the
annotation is documentary until one does — and it is the D-97 case, §4.1). The 30 remaining
series entries of the corpus are annotated `AMOUNT` by 0b5d2c6 (§3.4).

Acceptance: MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE passes under its own 2 : 1 (L1-SUB
116,600.00 / L3-SEATS 28,600.00; July 68,933.33 / 4,766.67; schedules 9,533.33 / 4,766.67). Codex
PRODUCTION-C1B-SERIES-BASIS-77cc618: annotated Case B, Case A and CHK-043 accepted at narrow scope;
the dated-basis controls (inception `AMOUNT` 132,000 with a modification-date `PER_BOOKED_TERM`
entry: 66,000 under D18_DEFAULT, 132,000 under INCEPTION_ALL) pass.

AD-30 figures (reported, not decided): the entry read as `PER_BOOKED_TERM` (the ruling's
annotation) gives 2 : 1 and the key's allocations; read as `AMOUNT` (the remaining-increments amount
as today) it gives 4 : 1 (L1-SUB 128,040.00 / L3-SEATS 17,160.00; July 70,840.00 / 2,860.00).
`PER_BOOKED_TERM` evidence must identify the term it prices (Codex: not proved for multi-modification
term extensions or fiscal calendars; part of AD-30).

### 2.6 Migration numbering (6e64380)

Lane P2 (sprint/l7) already carries alembic revision 0055 (T-PLT-06 `hmac_key_id` /
`canonical_version`), so the E-49 enum migration is `0056_e49_series_ssp_basis.py`, revision
"0056", `down_revision` "0054" (main's head at the lane's base). Single-head coordination:
whichever of P2 / C1b merges second re-parents its `down_revision` onto the other's revision
(linear history, one head; `backend/tests/pg/test_migrations.py::test_single_head`'s literal moves
with it — the lane sets it to "0056"). 04 rev 1.16, E-49 and T-REF-30 cite 0056; the OpenAPI
document does not embed the revision. Gates by exit code: `make lint` OK; architecture + unit
suites 510 passed.

## 3. Codex reviews of the lane's commits

### 3.1 PRODUCTION-C1B-ORIGINAL-FIVE-8e96309 and KEY-INPUT-DIFF-4fe4bb1

Accepted as recorded in §2.1 and §2.3; no further lane change.

### 3.2 PRODUCTION-C1B-ENCODED-JUDGEMENT-4778d5e → f5d39d9

Finding: `judgement_names_element` compared the outcome's raw element code with
`estimate_key.rpartition("/")[2]`, an encoded component (CV-21 percent-encodes `%`, `/`, `@`, `#`,
`:`), so a TY-06 code containing `/`, `#` or `:` (VC/CLAIM → K-01/VC%2FCLAIM) never matched: a
modelled enforceable claim stayed out (TP 9,700.00 against 10,700.00, no stage 04 finding) and a
valid POL-044 override stayed blocked (VC_TARGET_TOLERANCE_EXCEEDED against 355.56 / 2,444.44).
28 cases, 22 PASS / 6 FAIL. Reachability is qualified (the ordinary API Code regex rejects those
characters; the native bundle and TY-06 admit them).

Correction: `VcElementView` gains `element_code` (set from the pinned version at the three stage 04
construction sites); `judgement_names_element(outcome_key, estimate_key, element_code)` accepts the
encoded qualified key or the raw code exactly and never splits a key; vc.py and targeted.py pass the
element's code; the contract / obligation / book / authorisation checks are unchanged; the API
validation contract is untouched. Fail-first on 6e64380: the six raw-code cases (three claims,
three overrides) failed; encoded-qualified positives for the three characters and the wrong-element
(the split tail of the encoded key), wrong-contract, false-flag and other-book negatives stay green
(`test_s04_claim_gate.py`, 23 tests). Stages 01/04/05 + properties P01: 176 passed; lint OK;
typecheck OK. Codex's 28 review oracles are untouched for its retest.

### 3.3 PRODUCTION-C1B-SERIES-BASIS-77cc618 S1 and S2 → e8a1e3c

S1 (must fix): `series_basis_scale` counted the calendar months the term touches while ρ used the
convention's period weights (Jan 16 – Dec 31, `PER_INCREMENT` 11,000, 1 Jul amendment: 11,000 × 12
× 62/119 = 68,773.11 under MONTHLY_EVEN, 11,000 × 12 × 6/11 = 72,000 under MID_MONTH, against the
six remaining July–December increments, 66,000); `formulas._series_multiplier` repeated the count,
so replay accepted it. Correction: `progress.time_units` (ALG-11's own period count — the
denominator of `time_fraction`) and `progress.series_increments` (the term's increments in the
series unit as the convention counts them) are used by stage 06 and mirrored in the formula, which
also verifies the new additive param `series_remaining_increments` = increments × `remaining_scale`.
Measured (D18_DEFAULT and INCEPTION_ALL): MONTHLY_EVEN increments 357/31, ρ 62/119, remaining 6,
weight 66,000; MID_MONTH increments 11, ρ 6/11, remaining 6, weight 66,000; `PER_BOOKED_TERM` over
the partial term 132,000 × 62/119 = 68,773.11 (the booked-term reading); controls: 16 Jul amendment
66,000 under both conventions (July counts as remaining), DAILY day increments 365 / 184 remaining,
400 × 184 = 73,600; the full-term Case B figures unchanged.

S2 (must resolve and fix): the multiplier toggled on remaining quantity == 1 (12 units at
`PER_INCREMENT` 110, Jan–Dec, 1 Jul: remove 0 → 660, remove 10 → 110, remove 11 → 660 — a
removal raised the weight). Correction: the toggle is removed; `PER_INCREMENT` is value ×
increments × ρ × the remaining quantity, the quantity read as service units each spanning the term
(the S06-R-11 text for a quantity-one line, extended multiplicatively): 7,920 / 1,320 / 660 for 0 /
10 / 11 removed, monotone (7,920 / 7,260 / 3,960 / 1,320 / 660 for 0 / 1 / 6 / 10 / 11), multiplier
12 throughout; no reading is inferred from the quantity; the fixture is not special-cased. The
"quantity counts increments" reading needs a declaration the schema lacks — ruling request D-97,
§4.1; 04 rev 1.16 E-49 / T-REF-30 text amended (the clause withdrawn, D-97 cited).

Fail-first: the 16 tests of `test_s06_series_basis.py` run against a read-only snapshot of the
f5d39d9 engine (`git archive`, PYTHONPATH-first; `.run/l5-c1b/series-failfirst-f5d39d9.log`): 13
failed (S1 seven, S2 three, the base D-93 (4) tests for the new param, the DAILY control), 3 passed;
on e8a1e3c all 16 pass. Stages 05/06/09 + kernel: 461 passed, 5 xfailed; lint OK; typecheck OK.

### 3.4 PRODUCTION-C1B-SERIES-BASIS-77cc618 §3 (undeclared basis) → 0b5d2c6

Finding: the runner mapped an omitted basis to `AMOUNT`, the engine saw only the defaulted string,
and a test accepted the omitted case; the corpus inventory was incomplete (Case B's added-seats
entry omitted).

Inventory (`.run/l5-c1b/series_inventory.py`, `.run/l5-c1b/series-inventory.tsv`): 29 active
keys carry a `series` template; 34 SSP entries price a series product; 30 declared nothing —
ALC-BR-06, COST-CAP-COMMISSION, COST-S8 ×4, DISC-GE-06, DISC-S10-RPO-EX42 ×2, MOD-CHK-112,
MOD-FS-03 A/B (SAAS-SEATS-ADD6M), MOD-FS-09, MOD-FS-10 ×2, MR-FS-04, NCC-CHK-135, POB-BR-01,
POB-S2-EX12A, REC-FS-01, REC-FS-06, REC-RB-05, SFC-FS-11 A/B, SSP-FS-05, STP1-S1-EX1 B/C,
VC-CAP-USAGE, VC-CHK-110, VC-FS-02. Test fixtures: every direct `SspEntryInput` declares
`value_basis="AMOUNT"` (`test_s15_rpo`, `test_s06_proposal`, `test_s06_prospective`,
`test_s03_lines`, `allocation_worlds`, `golden_streams`, `cpc_worlds`); platform fixtures go through
the API / DB default (§4.2).

Correction: the 30 entries declare `value_basis: AMOUNT` with the note "declared
remaining-increments reading (the reading the key's oracle embodies); no value change" — the engine
already read an omitted basis as `AMOUNT`, so no expected value moves. Provenance: the loader keeps
an omitted basis as `None`, checks the E-49 literal and, for a product whose template is `series`,
refuses the omission at `/world/ssp_books/<i>/versions/<j>/entries/<k>/value_basis` ("declares no
`value_basis` (E-49: AMOUNT, PER_INCREMENT or PER_BOOKED_TERM; D-93 (4) fails closed)"); the
runner's `AMOUNT` default applies to non-series entries only (T-REF-30 default). dev-guide §9.5.3
`ssp_books`: the "fails closed once the corpus entries are annotated" sentence now states the active
refusal. The engine-level test is renamed to "explicit AMOUNT … is taken as is". Fail-first: the new
cross-validation case (`test_loader_validation.py`) found nothing before the loader change; after,
it is refused and the explicit-AMOUNT / non-series-omitted variant loads. unit/answer_keys + series
tests 126 passed; lint OK; typecheck OK.

For AD-30: seven annotated keys modify a contract that holds a series obligation — MOD-CHK-043
(`AMOUNT`, ruled), MOD-CHK-112 (SUB-24), MOD-FS-03 A/B (SAAS-SEATS-ADD6M, the added obligation's
own entry), MOD-FS-09 (SAAS-24M), MOD-FS-10 (PCS-3Y, SAAS-CONV-24M), REC-RB-05 (CAPITATION-PMPM).
`AMOUNT` there declares the reading their oracles embody today; whether any of those entries
evidences a booked term (`PER_BOOKED_TERM`, which would change values) is an SSP-evidence judgment
for the accountant, not decided here.

### 3.5 D-97 (3), (3a), (22) → 299e36a, 1434d07

Ruling (D-97 draft v1 items (3), (3a), (22); the lane's request of §4.1 as returned): T-REF-30
gains `quantity_unit` ∈ {`SERVICE_UNITS`, `INCREMENTS`}, nullable, REQUIRED for a `PER_INCREMENT`
entry and refused (CV-45) when absent on one, never inferred, no default; `SERVICE_UNITS` = value
× increments remaining under the pinned convention × ρ × remaining quantity; `INCREMENTS` = value
× ρ × remaining quantity; entries of one product in one book agree; K-02's seat-month entry is
`INCREMENTS`; the API refuses a `series` product's entry without an explicit `value_basis` and a
`PER_INCREMENT` entry without `quantity_unit` (422 `validation-failed`); the `'AMOUNT'` default
stays for non-series products; no backfill. (22): the unnamed-`EAC` membership reading of §4.3 is
confirmed; more than one booked obligation fails closed as today (no code change).

Docs first (299e36a, numbered against main 14ce0ff, then renumbered by fcc2b69 against eb5546a — 04 rev
1.19, ENGINE_SPEC rev 1.26, §3.6): 04 rev 1.17 at the time — the lane's 1.16 row renumbered
(it collided with ENG-D1's 1.16 on main) — E-131 `ssp_quantity_unit`, T-REF-30 `quantity_unit
erev.ssp_quantity_unit NULL` with `CHECK (value_basis <> 'PER_INCREMENT' OR quantity_unit IS NOT
NULL)`, E-49 note, the (3a) rule; ENGINE_SPEC rev 1.10 (after main's 1.9): the S06-R-11 series
sentence; dev-guide rev 1.32 (after main's 1.15): §9.5.3 `quantity_unit?`.

Code (1434d07): `SspEntryInput.quantity_unit`, `SspResolution.quantity_unit`; stage 01
`check_series_quantity_units` (CV-45 `ValueError`: absent on `PER_INCREMENT`; disagreement per
(`ssp_book_code`, `product_code`) across the bundle's versions); stage 06 `series_basis_scale`
multiplies by the increments under `SERVICE_UNITS` and by 1 under `INCREMENTS` (`parts[0]` already
carries value × remaining quantity), fails closed on any other unit, records
`series_quantity_unit`; `formulas._series_multiplier` mirrors it (ids unchanged). E-131
`SspQuantityUnit` in `erev_api.enums` and `erev_engine.enums`; migration 0056 also creates
`erev.ssp_quantity_unit`, the nullable column and the check (downgrade in reverse); the tables
module, `queries.py`, `resolution.py` carry the column. API: `SspEntryIn.value_basis` is optional —
`commands._series_products` (a product whose default POB template has a version of `series`
distinctness) makes the omission a 422 at `entries[i].value_basis`, a non-series omission stores
the T-REF-30 `'AMOUNT'` default; `entries[i].quantity_unit` for a `PER_INCREMENT` entry without
one and for a later entry of the same product declaring another unit; `SspEntryOut.quantity_unit`;
OpenAPI and `schema.d.ts` regenerated; the editor sends `value_basis` explicitly today and carries
no `quantity_unit` field — a `PER_INCREMENT` entry created there is refused until the ruled
frontend follow-up lands. Loader: `quantity_unit` in the key schema; refusals for a `PER_INCREMENT`
entry without it and for disagreeing units within a book; the runner passes it through. Fixtures:
K-02 `INCREMENTS`; the factory entries of the other series products (AVM-SUP-12, AVM-PLAT-100,
AVM-SEAT-MO) declare `AMOUNT` under (3a). No corpus key carries a `PER_INCREMENT` entry (§3.4
inventory), so no key changes.

Fail-first: `test_s06_series_basis.py` (22 tests) against a read-only snapshot of the 0b5d2c6
engine — 18 failed / 4 passed (`.run/l5-c1b/d97-failfirst-0b5d2c6.log`; the `INCREMENTS` fixture
cannot be expressed there); the two loader cases found nothing before the loader change. On
1434d07: series + unit/answer_keys + stages 01/05/06 + architecture 391 passed (the drift test now
expects E-1 to E-131 and mirrors 125 in the engine); lint OK; typecheck OK (backend + tsc); vitest
`ssp-book-version` 5 passed (fixture gains `quantity_unit: null`). The (3a) API test
(`tests/domain/ssp/test_ssp_books.py::test_d97_3a_…`) needs the database and runs in the chain.
Figures: `SERVICE_UNITS` 7,920 / 1,320 / 660 and `INCREMENTS` 660 / 110 / 55 for 0 / 10 / 11 of
12 units removed at 110 (shares of the 86,400.00 pool for remove 11 under `INCREMENTS`: 143.76 /
86,256.24), both under D18_DEFAULT and INCEPTION_ALL; monotone under both units.

### 3.6 D-97 (3) v3 completion contract → fcc2b69, 79b6742

The supervisor's v2/v3 draft (Codex's completion contract) refines (3): ρ enters once
(`SERVICE_UNITS` = value × the remaining increments — the term's increments under the pinned
convention × ρ — × the remaining quantity: 110 × 6 × 12 = 7,920; S1's quantity-one line 11,000 × 6
= 66,000; `INCREMENTS` = value × ρ × the remaining quantity: 110 × ½ × 12 = 660, then 110 / 55);
the supported meaning is the DECLARED one, neither is inferred, never both on one entry; a
`quantity_unit` with any other basis is refused; agreement scope is every dated entry of one
product identity within one book, validated on insert / update and again when a dated entry is
selected, an earlier entry never reinterpreted by a later declaration; compatibility: undeclared
existing entries fail closed for new computations, RCP-28 replay runs under its original schema
and runtime, adding a canonical field may change hashes and no byte-identical cross-version claim
is made; separate API tests; acceptance = the actual `INCREMENTS` path, shared trace
re-evaluation, the original conditional oracles 660 / 110 / 55 under both POL-080 bases. The
implementation at e8a1e3c / 1434d07 already multiplied ρ once (increments × ρ × quantity); the v3
work is the wording, the iff rule, the selection-time check, the book-wide API check, the hash
view and the migration correction.

Docs (fcc2b69; re-checked against main eb5546a at commit: 04 1.17 → the lane's row is 1.19 with
P2's 1.18 between; ENGINE_SPEC 1.10 (the D-97 docs lane) → the lane's row is 1.11; dev-guide 1.15 →
1.16): 04 E-131 / E-49 / T-REF-30 rows and the 1.19 revision row carry the v3 wording, the iff
check `CHECK ((value_basis::text = 'PER_INCREMENT') = (quantity_unit IS NOT NULL))`, the agreement
scope and the compatibility statement; ENGINE_SPEC S06-R-11 sentence likewise; dev-guide §9.5.3.

Code (79b6742): stage 01 `check_series_quantity_units` also refuses a unit on any other basis;
stage 05 `check_selected_quantity_unit(cb.bundle, book, entry)` re-validates the SELECTED dated
entry against every entry of its product in its book before the `SspResolution` is built;
`SspEntryInput.hash_view` / `SspVersionInput.hash_view` enter `InputBundle.sha256` with
`quantity_unit` only when declared (the D-93 (5) `direction` treatment) — measured: the undeclared
FS-03B-shaped world hashes `29cabfd5c874a23732fa5948929266b7b6074ab942775338f579e774c58330b2`
under the 0b5d2c6 engine (before the member existed) and under 79b6742
(`.run/l5-c1b/hash-compat.log`; same `engine_version`, so this is the chosen compatibility path
measured, not a cross-version claim); migration 0056's check compares `value_basis::text`
because PostgreSQL refuses the label the same revision adds as an enum literal before commit
("unsafe use of new value") — the 1434d07 measurement's unit step errored ten migration-applying
tests on exactly that (`measure-summary-1434d07.txt`: suites 1,566 passed / 10 errors, END FAILED;
the six affected modules pass after the fix, 17 passed); API `entry_errors` refuses a unit with any
other basis (`entries[i].quantity_unit`) and `quantity_unit_errors(drafts, stored)` compares the
request with `_book_quantity_units` — the book's stored entries across every version, leaving out
the current version's entries the request replaces; the loader refuses a unit with another basis.
CSV import admission: `SspEntryRowIn` inherits `SspEntryIn`, so the CSV columns carry
`quantity_unit` and both importers reach `upsert_ssp_entries`' rules; the legacy SKU importer
builds distinct / nondistinct parity products only.

Tests: `test_s06_series_basis.py` 27 tests — the `INCREMENTS` oracles 660 / 110 / 55 under
D18_DEFAULT and INCEPTION_ALL (multiplier 1, `series_quantity_unit` INCREMENTS), `SERVICE_UNITS`
7,920 / 1,320 / 660, monotone under both units, refusal without a unit, refusal of a unit with
`AMOUNT` / `PER_BOOKED_TERM`, disagreement refusal, the hash-view path; fail-first for the v3
additions against the 1434d07 engine snapshot 3 failed / 24 passed
(`.run/l5-c1b/d97v3-failfirst-1434d07.log`). Loader: a fourth cross-validation case (unit with
`AMOUNT`). API (`tests/domain/ssp/test_ssp_books.py`, DB — run in the chain): four separate
tests — omitted series basis refused at `entries[0].value_basis` and explicit `AMOUNT` stored;
non-series omitted → `AMOUNT` default, explicit `AMOUNT` / `PERCENT_OF_LIST` unchanged;
`PER_INCREMENT` unit rules (absent, with another basis, request disagreement, stored and listed);
book-wide agreement (a second version declaring another unit refused naming the stored unit, the
same unit accepted, a rewrite departing from the other version refused). On 79b6742: series +
unit/answer_keys + stages 01/05/06 + kernel + architecture 566 passed / 5 xfailed; lint OK;
typecheck OK (backend + tsc).

Admission (Codex control at 1434d07): with a region=US `INCREMENTS` entry STORED and a request
carrying a valid region=EU `SERVICE_UNITS` entry of the same product in the same version,
`upsert_ssp_entries` at 1434d07 validated the request alone and reached its INSERT; 79b6742
compares the request with the book's stored entries across every version (`_book_quantity_units`;
the current version's entries the request replaces are left out) and refuses at
`entries[i].quantity_unit` naming the stored unit. The engine's later CV-45 rejection (stage 01
bundle check, stage 05 selection check) does not establish prevention at admission — that is the
API test's job (`test_d97_3_quantity_unit_agrees_across_the_book`: the same-version stored-versus-
request control, a second version departing from the store, the same unit accepted; DB, run in the
chain) with the DB-free synthetic-store unit test `tests/unit/ssp/test_books_quantity_unit.py`.
04 API-S-SspEntry states the conditional `AMOUNT` default (non-series only) and the `quantity_unit`
member; the T-REF-30 `value_basis` row carries one ρ-once expression.

Contradictory retained population (Codex retest of 79b6742, supplemental 8/9): `_book_quantity_units`
kept the first stored unit per product, so rows of one product already declaring `INCREMENTS` in one
dated version and `SERVICE_UNITS` in another let a request matching the first reach the INSERT.
8f0a5a2 returns every unit the retained rows declare and `quantity_unit_errors` refuses every
request entry of such a product before anything is written, naming all stored units, whatever the
request declares; the historical rows are neither discarded nor reinterpreted; same-unit positives
and the other refusals are unchanged. Fail-first: synthetic-store unit tests 2 failed / 3 passed
against the a815678 snapshot (`.run/l5-c1b/contradiction-failfirst-a815678.log`), 5 passed after; the
DB control fabricates the contradiction below the API (the second version's stored row re-labelled)
and asserts the refusal on either version with nothing written (chain). Migration 0056 keeps
`down_revision` 0054 in the lane; re-parenting onto P2's 0055 and the single-head literal happen at
the second merge.

Disposition (supervisor wording): the six conditional failures of Codex's synthetic fixture were
failures until the declaration landed; under `quantity_unit: INCREMENTS` the original 660 / 110 /
55 expectations stand and are never rewritten to 660; the interim service-units implementation's
before/after effect on that undeclared fixture (pool 86,400: remove 0 1,694.12 / 84,705.88 →
16,722.58 / 69,677.42; remove 10 287.04 / 86,112.96 → 3,323.08 / 83,076.92; remove 11 unchanged)
is superseded interim state, never a pass; Case B's pool 85,800 is distinct from the synthetic
86,400; absent comparisons are not passes. S1 and the loader / corpus guard are closed by Codex's
retest of 0b5d2c6; S2 closes by the declaration member plus both readings verified plus the
fail-closed refusal when the member is absent.

Annotation inventory (per entry, with evidence; replaces any "every other entry is X" statement):

| Entry | Basis | Unit | Evidence |
|---|---|---|---|
| Corpus, every `PER_INCREMENT` entry | — | — | none exists: the 34 series-product entries of the 29 series keys are 30 `AMOUNT` (0b5d2c6 annotations, the reading each oracle embodies), MOD-CHK-043's 2 explicit `AMOUNT` (D-93 (4) ruled), MOD-FS-03 A/B `SAAS-SEATS-12M` `PER_BOOKED_TERM` (D-93 (4) ruled) |
| PRD K-02 factory `AVM-SEAT-MO` (`backend/tests/support/factories.py`) | `PER_INCREMENT` | `INCREMENTS` | the factory's own note "100 seats × 24 months as 2,400 seat-months, the unit of the SSP entry" (L4-2-Q-8); D-97 (3) names it; documentary until a platform test modifies a K-02 series obligation |
| Platform factories `AVM-SUP-12`, `AVM-PLAT-100`, `AVM-SEAT-MO` (K-11, PLATFORM-100 and SEAT-MO worlds) | `AMOUNT` | — | (3a) requires an explicit basis for a series product; the worlds' oracles embody the remaining-increments reading; no unit (not `PER_INCREMENT`) |
| Engine fixtures (`test_s06_series_basis.py`) | per test | per test | each test declares what it measures; the seats entry of the disagreement test is `PER_INCREMENT` / `INCREMENTS` on another product |
| API fixtures (`test_ssp_books.py::test_d97_*`) | per test | per test | each assertion names its declaration |

### 3.7 Codex review status (recorded verbatim from the supervisor's relays)

| Report | Head | Status |
|---|---|---|
| PRODUCTION-C1B-ORIGINAL-FIVE-8e96309 (3e069b4a…) | 8e96309 | five MOD keys 5/5, 110/110; e467e25 and parent 3e6c99a 0/5, 94/110 — change isolated |
| PRODUCTION-C1B-KEY-INPUT-DIFF-4fe4bb1 (17f4511f…) | 4fe4bb1 | 150 monetary checkpoints retained; not inputs-only (§2.3) |
| PRODUCTION-C1B-ENCODED-JUDGEMENT-4778d5e (891c0005…) | 4778d5e | 22/28, 112 checks 100/12 — six raw-code failures (§3.2) |
| PRODUCTION-C1B-ENCODED-RETEST-f5d39d9 (2306fa39…) | f5d39d9 | 28/28, 112/112; the six failures pass; negatives rejected; scope native stage 01 → 04/05 only, ordinary API/CSV Code grammar still rejects the affected characters, so stored-data / API reachability remains unproved |
| PRODUCTION-C1B-SERIES-BASIS-77cc618 (cf34399c…) | 77cc618 | annotated Case B / Case A / CHK-043 accepted at narrow scope; S1 must fix, S2 must resolve and fix, undeclared-basis guard unfinished (§3.3, §3.4) |
| PRODUCTION-C1B-SERIES-RETEST-0b5d2c6 (ad1d140d…) | 0b5d2c6 | S1 closed (66,000 under both conventions, D18 / INCEPTION); loader / corpus guard closed (35/35; 30 AMOUNT fields across 28 keys; removing them reproduces 77cc618 byte-for-byte); S2 open pending the declaration |
| frozen-source execution of 1434d07 | 1434d07 | provisionally green, 129/129 over 22 worlds and 17 expected refusals; INCREMENTS 660 / 110 / 55 under both policies (remove-11 shares 143.76 / 86,256.24), SERVICE_UNITS 7,920 / 1,320 / 660, S1 66,000, traces re-evaluate; defect: committed spec text double-prorated (fixed by fcc2b69 / f3c1dc3); admission gap QU-1 (fixed by 79b6742, evidence a815678) |
| PRODUCTION-C1B-CORRECTION-RETEST-79b6742 (08a2a48f…) | 79b6742 | QU-1 closes at the native-command boundary; original 15/15, financial 129/129; stage 05 selection 7/7; three CV-25 hash pairs match, explicit units hash distinctly; residual: retained-population contradiction (`setdefault`); QU-2 wording |
| PRODUCTION-C1B-RESIDUAL-CLOSURE-8f0a5a2 (e29433b9…) | 8f0a5a2 | stored-population residual and both QU-2 points closed: original admission 15/15; retained 9/9 plus three variants 12/12 (either declared unit, reversed retained order, AMOUNT / no-unit all refuse contradictory stored units before INSERT; input rows preserved); old literal harness 7/9 with two disclosed scalar-to-set shape adaptations; the 149 financial source modules unchanged, prior 129/129 retained. Scope: native command + mock DB boundary only — chain 7 (the pg admission test, test-pg, ci, parity) and the 0056 re-parenting at the second merge are the remaining evidence |

### 3.8 SSP-ADMISSION-R1 (joint with F-WEB-R) → 021a067, 053813f

Codex PRODUCTION-SSP-EDITOR-ADMISSION-ad8a117 (9f6ae136…): the editor required the explicit basis
when `ProductOut.distinctness_default === "series"`, while the API classified a product by its
default POB template having a `series` version — and product create / update let the two
attributes disagree; a `distinct` product with a published series default template saved
`value_basis: AMOUNT, quantity_unit: null` from the editor untouched, and the API's omission guard
cannot tell an auto-supplied `AMOUNT` from a deliberate one. Ruling (supervisor): (a) the
template-derived predicate is authoritative; (b) exposed on `ProductOut` as the derived, read-only
`requires_explicit_ssp_basis`, computed by the admission guard's code path; (c) the editor keys its
required-basis and quantity-unit UI to it (F-WEB-R); (d) explicit `AMOUNT` on a series product and
the non-series default stay; the differing-attribute control is a test on both sides; (e) the
product-model inconsistency itself is D-98 candidate PRODUCT-CLASS-CONSISTENCY, not fixed here.

Built: `domain.reference.products.series_product_ids(session, product_ids)` is the one predicate;
`domain.ssp.commands._series_products` delegates to it by product id; `queries.product_out` /
`list_products` / `product_row` add `requires_explicit_ssp_basis` from the same call (create /
update responses come through `product_row`); `ProductOut` gains the member (OpenAPI, `schema.d.ts`
regenerated). 04: no API-S-Product field table exists, so the member is stated on the API-R-23 row
and in the 1.19 revision row. Tests (DB, chain): `tests/domain/reference/test_products.py::test_ssp_
admission_r1_…` — no template → false; a `distinct` product with a series default template → true
(Codex's differing-attribute control); a units template → false; the list carries the flag; the
write schema refuses the member; `test_ssp_books._series_world` asserts the flag on both products
before the omission refusal and the explicit-`AMOUNT` acceptance. DB-free: unit ssp + loader +
OpenAPI export 20 passed; both API modules collect (24 tests); lint OK; typecheck OK (backend +
tsc).

## 4. Questions returned (not decided)

### 4.1 Ruling request D-97: what a series line's `quantity` counts under `PER_INCREMENT` — RULED (D-97 (3), §3.5)

T-REF-30 carries no member saying whether a series line's `quantity` counts service units (each
spanning the term — 12 subscriptions) or increments (1,200 seat-months). `PER_INCREMENT` is
therefore ambiguous for quantity ≠ 1, and Codex S2 showed that inferring the reading from the
current quantity makes a removal raise the weight. Implemented until ruled: the service-units
reading (weight = value × increments × ρ × remaining quantity). Proposed minimal representation:
T-REF-30 `quantity_unit` ∈ {`SERVICE_UNITS` (today's default), `INCREMENTS`}, required for a
`PER_INCREMENT` entry (refused, CV-45, when absent on one); the engine multiplies by increments × ρ
× quantity under `SERVICE_UNITS` and by ρ × remaining quantity under `INCREMENTS`; the key schema
and the SSP editor carry the member. Figures on Codex's fixture (12 units at `PER_INCREMENT` 110,
Jan–Dec, 1 Jul; remove 0 / 10 / 11): `SERVICE_UNITS` 7,920 / 1,320 / 660 (implemented);
`INCREMENTS` 660 / 110 / 55 (shares of the 86,400.00 pool for remove 11: 1,694.12 / 84,705.88
against 143.76 / 86,256.24). The K-02 seat-month factory entry (`PER_INCREMENT`) is the
`INCREMENTS` case; no platform test modifies a K-02 series obligation, so no oracle changes either
way. Alternatives not taken: refusing every `PER_INCREMENT` entry until ruled (blocks the ruled
FS-03 / K-02 annotations); the increments reading for all quantities (contradicts S06-R-11 for a
quantity-one line: 11,000 × 1 × 1/2 = 5,500 against 66,000).

### 4.2 The API / DB side of "fails closed" — RULED (D-97 (3a), §3.5)

T-REF-30 `value_basis` is NOT NULL with default `'AMOUNT'`, so a POST without the member stores an
`AMOUNT` declaration: through the API and the platform fixtures an omitted basis is
indistinguishable from an explicit one. The lane activated the refusal where provenance exists (the
answer-key loader, §3.4) and changed no column default. Whether the API should require an explicit
basis for a series product's entry (a schema-level refusal, dropping the default for series
products) is returned with 4.1.

### 4.3 D-92 (1a) membership of an unnamed `EAC` element — CONFIRMED (D-97 (22))

Read as "the contract's only booked obligation is amended" (mirroring stage 09 `eac_keys` and stage
11 `_names_unit`); every corpus `EAC` element with an amendment names its obligation, so no key
exercises the unnamed case.

### 4.4 AD-28 and AD-30

Stay with the independent accountant; both readings' figures are in §2.1, §2.5 and §3.4.

## 5. Per-key state (the ten acceptance keys)

| Key | Base 3e6c99a | After | Ruling |
|---|---|---|---|
| MOD-CHK-027-S6-EX8 | `catch_up_modification_cum` 76,829.26 vs 91,463.41 | PASS | D-92 (1) |
| MOD-CHK-042-D18 | revenue 70,880.00 vs 70,918.92; B 77,200.00 vs 77,297.30 (9 mismatches) | PASS | D-92 (1) (AD-28) |
| MOD-CHK-042-INCEPTION | 8,000.00 vs 2,000.00 | PASS | D-92 (1) |
| MOD-CHK-115 | modification 0.00 vs (15,555.56); estimate (15,555.56) vs 0.00 (4) | PASS | D-92 (1) |
| MOD-S6-COMBINED-MOD-OWN | 20,571.43 vs (5,142.86) | PASS | D-92 (1) |
| REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST | trace `catch_up:BR-08/L1-TOOL:FY2026-P04` absent | PASS | D-92 (2) |
| MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM | trace node absent; TP 5,480,000.00 vs 5,580,000.00 (23) | PASS | D-92 (2), D-93 (3) |
| MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE | July REVENUE 9,900.00 vs 15,400.00 | PASS | D-93 (1) |
| MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE | L1-PROTO 1,800,000.00 vs 1,500,000.00; L2-UNITS quantity 2 vs 5 (20) | PASS | D-93 (2) |
| MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE | L1-SUB 128,040.00 vs 116,600.00 (20) | PASS | D-93 (4) (AD-30) |

## 6. Gates

### 6.1 Measured on 77cc618 (superseded head; kept as evidence)

| Gate | Result | Log |
|---|---|---|
| `make lint` / `make typecheck` | OK / OK (562 files) | `.run/l5-c1b/lint-10.log`, `typecheck-5.log` |
| engine + architecture + unit | 1,543 passed, 5 xfailed | `.run/l5-c1b/suites-2.log` |
| vitest `ssp-book-version` | 5 passed | `.run/l5-c1b/vitest-ssp.log` |
| `make answer-keys` ten C1b ids / 192 selection / all active | 10/10; 192/192; 243 selected, 203 passed, 38 failed, 2 withdrawn (no new failure vs the base list; 20 turned green) | `keys-final.log`, `keys-selection.log`, `keys-all.log` |
| `make properties` | OK, exit 0 | `.run/l5-c1b/properties.log` |

### 6.2 Measured on 053813f (the head for merge)

Filled in §7 as each run ends (`.run/l5-c1b/measure-summary.txt`; chain `.run/l5-c1b/chain9/`).

### 6.3 Chain 9 on 053813f (the DB stages) and the ci-fix targeted runs

Chain 9 (`.run/l5-c1b/chain9/summary.txt`; slot 1 claimed after the interim batch's claim, per the
supervisor's ordering condition): parity filtered 121 / 121 OK; parity unfiltered 121 / 122 (the
deferred GPB-3 `point_in_time_equivalence::shipped-db-equivalence` reader, unchanged state);
test-pg 289 / 1 (`test_dg_arc_09_pg_enum_labels_equal_python` asserting `122 - 14` while 0056 adds
E-131 `ssp_quantity_unit`); **ci FAIL rc=2 46m — backend 2,610 passed, 50 failed, 5 skipped**
(21 FAILED + 29 ERROR); END 18:06:31, lock and slot released as owner.

The 50 are DB-stage regressions of this lane's own D-97 work that the CPU measurement could not see,
three causes (all from `chain9/ci.log`):

1. 29 ERROR at fixture setup + 12 FAILED (`test_explain_api` 7, `test_activation` 9,
   `test_computation` 8, `test_balances_reports` 5, `test_rpo_disaggregation` 9,
   `test_policy_overrides` 2, `test_report_runs`, `test_me`, `test_dashboard_home`): the shared test
   worlds post SSP entries for series products (TPL-SUB-DAILY: PLATFORM, SEAT_MONTH, the zero-priced
   seats) without `value_basis` and receive the D-97 (3a) 422 (`entries[0].value_basis`, T-REF-30).
   Fix = input clarification in the test support (`point_entry` gains a `value_basis` kwarg;
   `report_world`, `seat_world`, `test_computation`, `test_explain_api` and `test_policy_overrides`
   declare `AMOUNT`, the corpus annotation) — no product-code change. `test_me` asserted the schema
   revision literal `0054` → `0056`.
2. 5 FAILED in `test_ssp_books.py` + 1 in `test_products.py`: `_series_world` and the R1 test's
   `_template` created DRAFT template versions, which T-REF-20 has always refused as a default
   (`templates.has_published_version`); these tests of this lane had never run green against the
   database — the earlier claim that they were verified was wrong. Fix: both worlds publish their
   version through an approver (`published_template`), products created first so the case line
   resolves. `test_book_version_and_entries` compared the entry shape to a literal lacking the new
   `quantity_unit: None` member (added).
3. The enum-count constant `123 - 14` (approved by the supervisor).

Targeted runs under the 16:08 amendment (`.run/l5-c1b/targeted-db-run.sh`: one pytest process, the
l5 chain lock taken and released as owner, `EREV_ENV=test` → this lane's database, perl alarm 300 s;
summaries `targeted-<tag>.summary`):

| Tag | Start → end | Selection | Counts |
|---|---|---|---|
| A | 18:23:08 | ssp books + products + pg drift | rc 127 (macOS has no `timeout`; nothing ran) |
| A2 | 18:24:32 → 18:25:05 | `tests/domain/ssp/test_ssp_books.py`, `tests/domain/reference/test_products.py`, `tests/pg/test_data_model_drift_pg.py` | 25 passed |
| B | 18:25:19 → 18:26:30 | `tests/domain/reports/test_rpo_disaggregation.py`, `test_balances_reports.py` | 16 passed |
| C | 18:26:30 → 18:27:42 | `tests/domain/contracts/test_activation.py`, `test_computation.py` | 12 passed, 8 errors (its own world's PLATFORM entry: cause 1) |
| D | 18:29 → 18:30 | api `test_explain_api`, `test_me`, `test_dashboard_home`, `test_report_runs`; `policies/test_policy_overrides` | 5 errors + 3 failed (cause 1 in their own worlds; the `0054` literal) |
| C2 | 18:34:28 → 18:36:05 | contracts (both files) | 19 passed, 1 failed (`test_ssp_snapshot_survives_later_publication`: its second version's PLATFORM entry) |
| D2 | 18:36:05 → 18:37:24 | api + policies (as D) | 26 passed |
| C3 | 18:38:23 → 18:38:41 | `test_computation.py -k test_ssp_snapshot_survives_later_publication` | 1 passed |

Every test that failed or errored in chain 9's ci is green in A2 / B / C2+C3 / D2 on the fixed tree.
The single DB chain runs once more on the final head (re-parented 0056 → 0055 after the P2 merge,
enum fix included), per the supervisor; until then CPU re-verification only (`measure.sh`).

### 6.4 Measured on d80c124 (the ci-fix head; CPU re-verification, `measure-summary.txt` START 18:42:34)

Ten keys 10 / 10; 192 selection 192 / 192; all active 203 / 38 / 2 withdrawn, zero new failures,
20 turned green (the same set as on 053813f); engine + architecture + unit 1,586 passed / 5 xfailed;
`make properties` OK; END OK 18:55:14; `properties.done` written. No engine or API code changed
between 053813f and d80c124 (tests and test support only), so the CPU picture is unchanged; the DB
stages are re-run once on the final re-parented head.

## 8. Re-parent preparation (branch-local, before the merge of main; supervisor assignments 2026-09-20)

Applied on `sprint/l5` without merging main (main was frozen red on one EX42 unit test; the merge
happens at the green head the supervisor announces):

| Item | Provisional (as committed) | Assigned | Where swept |
|---|---|---|---|
| 04 revision row | 1.19 (D-93 (4) landing; D-97 (3) `quantity_unit`) | **1.41** (ENG-C4 holds 1.40) | header entry, log row, E-49 / E-131 / T-REF-30 / API-S-SspEntry "rev" citations |
| ENGINE_SPEC row | 1.11 (S06-R-11 series row) | **1.26** (T1 1.25) | header entry, log row, S06-R-11 citation |
| dev-guide row | 1.16 (§9.5.3 `quantity_unit`) | **1.32** (T1 1.29–1.31) | header entry, log row, §9.5.3 text |
| 03-REQUIREMENTS row | none (REQ-MOD-011 sentence added under D-93 (2)) | **provisional 1.6**; main's 03 maximum observed at this writing: **1.5** (D-96) — the supervisor assigns the number at the merge | header entry, new log row |
| Enumeration | E-125 `ssp_quantity_unit` | **E-131** (E-125–E-130 are lane P5's, D-96) | 04 §3.4 row + every lane citation (T-REF-30, API-S-SspEntry, header, log row); both `enums.py` docstrings; dev-guide row and §9.5.3; DB enum type name unchanged |
| Drift pins | `range(1, 126)`, `ENGINE_ENUMERATIONS` ∋ 125, pg `123 − 14` | `range(1, 132)`, `ENGINE_ENUMERATIONS` ∋ 131, pg `131 − 2 − 14` | `tests/architecture/test_data_model_drift.py`, `tests/pg/test_data_model_drift_pg.py` (the api-only range `range(111, 125)` is left for the merge to bring main's P5 value) |
| Migration | `0056_e49_series_ssp_basis.py`, revision "0056", down "0054" (collides with main's 0055 P5 and 0056 F-LMG) | **`0060_e49_series_ssp_basis.py`, revision "0060", down_revision "0059"** — renamed only when F-CLO's 0059 is on main (kept out of the tree until then, as P4 did for F-LMG); head pins `tests/pg/test_migrations.py:101` and `tests/api/test_me.py:183` → "0060" then | — |

Consequence recorded plainly: with `range(1, 132)` and E-131 present while E-126–E-130 are not yet on
this branch, `test_data_model_drift` is red on `sprint/l5` until main is merged (captured below); the
pg pin cannot be checked against this lane's database before the merge for the same reason (the
database holds 109 enum types today).

Owed at and after the merge (supervisor's list): Codex retest target = the final re-parented head
(053813f and d80c124 are unreviewed; the last closure is 8f0a5a2); one end-to-end DB chain on that
head (slot on the supervisor's word); the ENGINE_VERSION bump per DG-ENG-10 at merge — level and
reason: the `quantity_unit` member enters the CV-25 hash view only when declared, so every existing
trace and input hash is unchanged (`hash-compat.log` 29cabfd5…) EXCEPT the keys that now declare
`PER_INCREMENT` / `INCREMENTS` (K-02 world; corpus keys annotated `AMOUNT` add a declared member and
change their input sha256 too), and the S06-R-11 series scale changes the trace params of series
segments — a batch-level `ENGINE_VERSION` bump at the merge (the same level the ENC-8 trace-param
change took), not a lane-level one, because no formula id or value semantics changed for undeclared
inputs; AD-28 / AD-30 stay with the independent accountant (G12); D-98 candidate
PRODUCT-CLASS-CONSISTENCY stays returned.

## 9. Merge of main (green head c60529ab, then the wave-end head 065e7f65)

**c60529ab** (F-RPS follow-up; merged first, 2026-09-20 02:4x). Ten conflicts, resolved by hand:
`erev_engine/bundle.py` — `InputBundle.sha256` keeps both hash-view members (this lane's declared
`quantity_unit` through `SspVersionInput.hash_view`, main's `PostedAmountInput.hash_view` reason
codes); `erev_engine/progress.py` — `__all__` keeps both `right_to_invoice_fraction` (ENC-6) and
`series_increments`; `s01_canonicalize/__init__.py` — ENC-6's right-to-invoice exemption beside this
lane's `pins.build(..., contracts=bundle.contracts)` (D-92 (1a)); `tests/api/test_me.py` and
`tests/pg/test_migrations.py` — main's head pins ("0055" / "0056" F-LMG) while the lane migration is
held out; `test_data_model_drift.py` and `test_data_model_drift_pg.py` — the lane's merged-state pins
(`range(1, 132)`, pg `131 − 2 − 14`); 04 — header 1.41 ahead of F-LMG's 1.36, log row after 1.36, the
E-131 row placed after P5's E-130 (ascending); ENGINE_SPEC — 1.26 ahead of 1.22; dev-guide — 1.32
ahead of 1.26, the §9.5.3 `ssp_books` row with `quantity_unit?` beside F-RPS's `fx_rate_sets` /
`rule_sets` members. OpenAPI regenerated (`make openapi`).

**Migration held out.** `0056_e49_series_ssp_basis.py` (revision "0056" on "0054") collides with
main's `0056_lmg_t_mig_01_03.py`; removed from the tree in this merge and kept at
`.run/l5-c1b/held-migration/`; it returns as `0060_e49_series_ssp_basis.py` (revision "0060",
down "0059") with both head pins → "0060" when F-CLO's 0059 is on main. Consequence (captured):
`test_dg_arc_09_every_database_enum_has_a_migration_type` is red until then — the ORM declares
`ssp_quantity_unit` without a migration in the tree.

**Captured statuses** (`.run/l5-c1b/statuses-merge-c60529ab.log`, 02:42:06–02:56:00): typecheck
rc=0; lint rc=0; architecture + governed-docs + layout rc=1 — 83 passed / 1 failed (the held-out
migration test above; DG-ARC-09 `enums_match_data_model` green with E-131); focused C1b (unit
answer_keys + ssp, engine s01 / s04 / s06) rc=0, 639 passed; release selection rc=0, 220 / 220;
engine + unit rc=1 — 2,550 passed / 1 xfailed / 2 failed: `test_privacy_classification`
`test_prv_01_catalogue_covers_every_code_column` and `…matches_04_tables` — P8's PRV-01 catalogue
lacked this lane's new column `ssp_entry.quantity_unit`; classified with `value_basis`
(`SPEC_C2_CONFIG`, configuration data, no personal data) in `erev_api/privacy/classification.py`;
the two tests re-run green (rc appended to the same log).

**Codex source binding, correction.** PRODUCTION-C1B-PREPARENT-SOURCE-REVIEW-5af7ed2b.md (39
artifacts) binds the calculation / hash / trace paths and all 243 keys to the reviewed evidence
(imported-module differences at 5af7ed2b = the two enum docstrings only); the prior 129 / 129
financial assertions and 053813f's 11 / 11 synthetic-SQL projection controls are source-bound, so
053813f is partially reviewed — not "wholly unreviewed" as §8 first said; d80c124's test-world fixes
remain unreviewed. Codex's conditional exact-original retest plan targets the final re-parented head.

**065e7f65** (wave end, COMMIT 25; merged on f8fc63ed). Two conflicts, both revision tables:
ENGINE_SPEC — header 1.26 ahead of ENG-C8's 1.23, log row after 1.23; dev-guide — header 1.32
ahead of P1's 1.28. OpenAPI regenerated. Captured statuses
(`.run/l5-c1b/statuses-merge-065e7f65.log`, 03:42:02–03:57:44): typecheck rc=0; lint rc=0;
architecture + governed-docs + layout + privacy rc=1 — 95 passed / 1 failed, the same
`test_dg_arc_09_every_database_enum_has_a_migration_type` (expected while 0060 is held out;
DG-ARC-09 `enums_match_data_model` and the PRV-01 catalogue tests green); focused C1b rc=0, 639
passed; release selection rc=0, 220 / 220; engine + unit rc=0, 2,564 passed / 1 xfailed. Prep done;
0060 on 0059 held out; the re-merge with the migration and both head pins follows the supervisor's
announcement of F-CLO's landed head. Governed files for merge-revrows: 04, ENGINE_SPEC, dev-guide,
03-REQUIREMENTS (the enumeration lives in 04 §3.4; no separate revision table).

## 10. Large re-merge — main 05c30117 (F-CLO landed; 0059 on 0058) and the migration restored

Merged 05c30117 on fdb836a6 without rebase. `git merge-tree --write-tree --name-only $(git rev-parse
main) HEAD` before the commit (main 05c30117, HEAD fdb836a6; `.run/l5-c1b/merge-tree-05c30117.txt`):
tree 8a941f4c…; conflicts `docs/04-DATA_MODEL.md`, `docs/accounting/ENGINE_SPEC.md`,
`docs/dev-guide.md`; auto-merged `backend/erev_api/enums.py`, `backend/erev_engine/formulas.py`,
`backend/erev_engine/stages/s05_allocation/__init__.py`, `backend/tests/architecture/test_data_model_drift.py`,
`backend/tests/support/answer_keys/loader.py`, `docs/api/openapi.json`, `frontend/src/lib/api/schema.d.ts`.

Header cells resolved by hand, both sides strictly descending, every log row kept: 04 → `1.50, 1.43,
1.41 (this lane), 1.40, 1.39, 1.38, 1.37, 1.36, …` with the 1.41 log row between 1.40 and 1.43;
ENGINE_SPEC → `1.26 (this lane), 1.24, 1.23, 1.22, …` with the 1.26 row after T1F's 1.24;
dev-guide → `1.41, 1.37, 1.35, 1.34, 1.32 (this lane), 1.28, …` with the 1.32 row before F-LMG's
1.34. No conflict markers remain in any tracked file (`git grep` of the three marker forms: 0).

Migration restored: `.run/l5-c1b/held-migration/0056_e49_series_ssp_basis.py` →
`backend/erev_api/db/migrations/versions/0060_e49_series_ssp_basis.py`, `revision = "0060"`,
`down_revision = "0059"` (F-CLO `clo_6_reconciliation_period_lock_id`); the module imports
`erev_api.db.migration_ops` only and passes literal labels (`("PER_INCREMENT", "PER_BOOKED_TERM")`,
`("SERVICE_UNITS", "INCREMENTS")`) — DG-MIG-12 (`test_migration_enum_literals`) green; docstring
re-pointed to E-131 / 04 rev 1.41 and the re-parent history. Both Alembic pins moved together:
`tests/pg/test_migrations.py:106` and `tests/api/test_me.py:187` "0059" → "0060". Two frontend
fixtures of main's `frontend/src/routes/settings/product.test.tsx` gained this lane's schema members
(`requires_explicit_ssp_basis: false`, `quantity_unit: null`) — tsc had refused them.

Captured statuses (`.run/l5-c1b/statuses-merge-05c30117.log`, 08:13:06–08:24:49 + the two fixes):
openapi rc=0; lint rc=2 (E501 in the 0060 docstring) → reflowed → **lint rc=0** (incl. the
single-head check at 0060); typecheck rc=2 (tsc: the two fixtures above) → fixed → **typecheck
rc=0**; architecture + governed-docs + layout + privacy rc=0, 98 passed (`every_database_enum_has_a_
migration_type` green again with 0060 in the tree); focused C1b rc=0, 642 passed; release selection
rc=0, 220 / 220; CPU set (engine + architecture + unit minus the six DB-fixture modules) rc=0,
2,721 passed / 1 xfailed. Interim head recorded in §7; one small re-merge (main d3166d0a = P5, then
F-CTR / ENG-C8) precedes READY.

## 11. Final small re-merge — main 30e9709f (F-CTR landed; P5 d3166d0a and COMMIT 33 underneath) — READY

Pre-check `git merge-tree --write-tree --name-only $(git rev-parse main) HEAD` (main had moved to
b179900b = F-CTR's docs-only ENGINE_SPEC_B repair, HEAD 8a971c07; `.run/l5-c1b/merge-tree-30e9709f.txt`):
tree 594a62a9…; conflicts `docs/04-DATA_MODEL.md`, `docs/dev-guide.md`; auto-merged
`backend/tests/architecture/test_data_model_drift.py`, `backend/tests/support/factories.py`,
`docs/api/openapi.json`, `frontend/src/lib/api/schema.d.ts`. Merged 30e9709f on 8a971c07 without
rebase; the two header cells resolved as descending unions, every row kept: 04 → `1.50, 1.49 (P5),
1.45 (F-CTR), 1.43, 1.41 (this lane), 1.40, 1.39, 1.38, 1.37, …` with main's separated `Closes` /
`Inputs` rows; dev-guide → `1.41, 1.40 (P5), 1.37, 1.36 (P5), 1.35, 1.34, 1.32 (this lane), 1.28, …`;
ENGINE_SPEC untouched by this merge (1.26 first). Staged tree verified: `git diff --cached --check`
reports only pre-existing trailing whitespace in F-CTR's own record; marker grep over tracked files 0;
`0060_e49_series_ssp_basis.py` revision "0060" on "0059"; both pins "0060". OpenAPI regenerated.

Captured statuses (`.run/l5-c1b/statuses-merge-30e9709f.log`, 09:15:08–09:26:33): openapi rc=0;
**lint rc=0** (single head 0060); **typecheck rc=0**; architecture + governed-docs + layout +
privacy **rc=0, 100 passed**; focused C1b **rc=0, 642 passed**; release selection **rc=0, 220 / 220**;
CPU set (engine + architecture + unit minus the six DB-fixture modules) **rc=0, 2,781 passed / 1
xfailed**. READY for merge-revrows as step c1b (after ENG-C8 and F-RPS); governed files 04 (1.41),
ENGINE_SPEC (1.26), dev-guide (1.32), 03-REQUIREMENTS (1.6). DB stages: not run in the lane since
chain 9 (§6.3, all failures fixed by targeted runs); measured by the integrated batch on merged main.
Codex retest target = the landed head.

### 11.1 Addendum — final re-merge of main d3a89805 (F-RPS landed; ENG-C8 underneath)

Pre-check `git merge-tree --write-tree --name-only $(git rev-parse main) HEAD` (main d3a89805, HEAD
05695287; `.run/l5-c1b/merge-tree-d3a89805.txt`): tree 81644629…; conflicts `docs/04-DATA_MODEL.md`,
`docs/dev-guide.md`; `backend/tests/support/answer_keys/runners.py` auto-merged (F-RPS's platform
runner beside this lane's loader / `quantity_unit` refusals — the focused suite exercises both).
Merged d3a89805 on 05695287 without rebase; the two header cells resolved as descending unions —
main's clause set verbatim, this lane's entry placed in order: 04 → 1.50 1.49 1.45 1.44 1.43 1.41 1.40 1.39…; dev-guide → 1.42 1.41 1.40 1.38 1.37 1.36 1.35 1.34 1.32 1.28…;
every log row kept; ENGINE_SPEC and 03 untouched by this merge. DG-ARC-14 row-width check against the
merged log headers: 04 row 1.41 — 4 cells / header 4; dev-guide row 1.32 — 5 / 5; ENGINE_SPEC row
1.26 — 4 / 4; 03-REQUIREMENTS row 1.6 — 3 / 3 (its header is still three columns on this head; F-ADM
widens it after this lane lands and repairs rows then) — no shape fix needed. Marker grep over tracked
files: 0; `0060_e49_series_ssp_basis.py` "0060" on "0059"; both pins "0060". OpenAPI regenerated.

Captured statuses (`.run/l5-c1b/statuses-merge-d3a89805.log`, 10:43:34–10:54:25): openapi rc=0;
**lint rc=0** (single head 0060); **typecheck rc=0**; architecture + governed-docs + layout +
privacy **rc=0, 100 passed**; focused C1b **rc=0, 660 passed**; release selection **rc=0, 220 /
220**; CPU set (engine + architecture + unit minus the six DB-fixture modules, excluded because the
lane database is not at 0060 and DB stages belong to the integrated batch) **rc=0, 2,805 passed / 1
xfailed**. READY as chain line c1b.

## 7. Run log

- 3e6c99a fail-first: the ten acceptance keys 0 passed / 10 failed with the mismatches of §5
  (`.run/l5-c1b/keys-base.log`).
- 8e96309: `test_s06_same_date_versions.py` 6 passed (fail-first 6 failed); engine + architecture +
  unit 1,531 passed / 5 xfailed; five MOD keys 5/5; lint OK; typecheck OK.
- 4fe4bb1: MOD-GE-02 (22 remaining mismatches, claim gate), REC-BR-08, MOD-GE-08, MOD-FS-03-CASEA
  pass; loader unit tests 110 passed.
- 4778d5e: `test_s04_claim_gate.py` 8 passed (fail-first 6 failed / 2 passed); stages 01/04/05
  159 passed; MOD-GE-02 passes; lint OK; typecheck OK.
- 77cc618: `test_s06_series_basis.py` 4 passed (fail-first 3 failed / 1 passed); stage 06 suite 133
  passed; engine + architecture + unit 1,543 passed / 5 xfailed; vitest ssp-book-version 5 passed;
  MOD-FS-03-CASEB, -CASEA, MOD-CHK-043 3/3; `make openapi` regenerated; lint OK; typecheck OK; the
  ten keys 10/10, the 192 selection 192/192, all active 203 / 38 / 2 with zero new failures against
  `/Users/rsang/dev/erev/.run/l9bgate/keys-all-failed.txt` (20 turned green: the ten C1b keys and
  the ten ENC-5 keys already green on main since cfa80f4); `make properties` OK.
- Chain 16033 (started 13:53:07 on 77cc618, `.run/l5-c1b/gates-chain.sh`): never claimed a slot and
  ran no stage (both slots held by l9 50998 and PID 81467); stopped by the lane at the supervisor's
  authorisation (verified: no `gate-slot-*.d/owner` names 16033, no l5 DB stage, the only child a
  `sleep`) so that the DB chain runs on the corrected head; `.run/l5-c1b/chain/summary.txt`.
- 6e64380: lint OK; architecture + unit 510 passed (`.run/l5-c1b/rename-tests.log`).
- f5d39d9: `test_s04_claim_gate.py` 23 passed (fail-first 6 failed / 17 passed on 6e64380,
  `.run/l5-c1b/encoded-failfirst.log`); stages 01/04/05 + P01 176 passed; lint OK; typecheck OK.
- e8a1e3c: `test_s06_series_basis.py` 16 passed (fail-first against the f5d39d9 engine snapshot: 13
  failed / 3 passed, `.run/l5-c1b/series-failfirst-f5d39d9.log`); stages 05/06/09 + kernel 461
  passed / 5 xfailed (`.run/l5-c1b/s1s2-tests.log`); lint OK; typecheck OK.
- 0b5d2c6: the loader cross-validation case fail-first (no finding,
  `.run/l5-c1b/loader-guard-failfirst.log`); unit/answer_keys + series tests 126 passed
  (`.run/l5-c1b/loader-guard-tests.log`); lint OK (`lint-15.log`); typecheck OK (`typecheck-8.log`).
- 0b5d2c6 re-measurement (`.run/l5-c1b/measure.sh`, DB-free; `measure-summary.txt` ends `END OK`
  only when every step is green): ten keys 10/10; 192 selection 192/192; the rest below as it lands.
- Chain 94436 (`.run/l5-c1b/gates-chain-2.sh`, START 14:27:02 head 0b5d2c6) was launched before
  the lane saw the 14:17 PDT per-worktree-lock amendment and takes no `.run/gates/chain-lock.d`, so
  its results would be invalid; it claimed nothing, was parked (its marker path made a directory,
  so its wait could never end) and was stopped by the lane at the supervisor's authorisation by its
  exact PID (verified: no slot owner, no lock owner, no stage). Replacement
  `.run/l5-c1b/gates-chain-3.sh`, PID 6666, START 14:33:26 head 0b5d2c6: waits for the
  measurement's `END OK` and the green marker (aborts on `END FAILED`), waits for 22:30:00Z (the
  supervisor's not-before for global claims), takes the worktree lock (mkdir-atomic
  `.run/gates/chain-lock.d`, owner PID + `ps lstart` + script name; refuses, does not queue, when an
  alive or unknown owner holds it), then the global slot, and releases lock and slot in one trap
  only when their owner files name its PID; log dir `.run/l5-c1b/chain3/`.
- Chain 6666 stopped by the lane at the supervisor's authorisation (D-97 (3)/(3a) change the
  engine and the schema): it had passed its MEASURE-OK line and was holding for 22:30Z; no slot, no
  lock, no stage (`.run/l5-c1b/chain3/summary.txt`). The 0b5d2c6 measurement had ended green
  (`measure-summary-0b5d2c6.txt`: ten keys 10/10; 192 selection 192/192; all active 203 / 38 / 2,
  zero new failures, 20 turned green; engine + architecture + unit 1,570 passed / 5 xfailed;
  properties OK).
- 299e36a, 1434d07: §3.5 gates (391 passed; lint; typecheck backend + tsc; vitest 5; fail-first
  18 / 4 on the 0b5d2c6 snapshot).
- 1434d07 re-measurement (`.run/l5-c1b/measure.sh`, fresh `measure-summary.txt`) and chain 4
  (`.run/l5-c1b/gates-chain-4.sh`, PID 52761, START 15:14:05 head 1434d07, dirty = this record):
  END OK + marker → 22:30:00Z → l5 lock → global slot → parity filtered, parity, test-pg, ci → one
  trap releases lock and slot as owner only; results below as they land.
- Chain 52761 (chain 4) stopped by the lane by exact PID before the v3 head change (no slot, no
  lock, no stage; `.run/l5-c1b/chain4/summary.txt`). The 1434d07 measurement ended `END FAILED`
  (`measure-summary-1434d07.txt`): ten keys 10/10, 192 selection 192/192, all active 203 / 38 / 2
  with zero new failures, properties OK, but the unit step errored ten migration-applying tests on
  the enum-literal check (§3.6) — the defect the v3 commit fixes.
- fcc2b69, 79b6742: §3.6 gates (566 passed; lint; typecheck backend + tsc; fail-first 3 / 24 on
  the 1434d07 snapshot; migration modules 17 passed; hash compatibility measured).
- 79b6742 re-measurement (`.run/l5-c1b/measure.sh`, fresh `measure-summary.txt`) and chain 5
  (`.run/l5-c1b/gates-chain-5.sh`, PID 5018, START 15:37:33 head 79b6742, dirty = this record):
  END OK + marker → 22:30:00Z → l5 lock → global slot → parity filtered, parity, test-pg, ci → one
  trap releases lock and slot as owner only; results below as they land.
- Chain 5018 (chain 5) stopped by the lane by exact PID before the Codex corrections changed the
  head (no slot, no lock, no stage; `.run/l5-c1b/chain5/summary.txt`). The 79b6742 measurement was
  left to finish (`measure-summary-79b6742.txt`; its engine code equals a815678's — the two later
  commits are docs and tests).
- f3c1dc3, a815678: 11 passed (synthetic-store unit tests + loader cases); the API module collects
  16 tests; lint OK; typecheck OK.
- 79b6742 measurement (`measure-summary-79b6742.txt`): ten keys 10/10; 192 selection 192/192; all
  active 203 / 38 / 2, zero new failures, 20 turned green; engine + architecture + unit 1,585 passed
  / 5 xfailed; properties OK; END OK. Chain 6 (`gates-chain-6.sh`, PID 27392, START 15:48:48 head
  a815678, launched by `relaunch-after-measure.sh`) was stopped by the lane by exact PID before the
  contradiction fix changed the head (no slot, no lock, no stage; `.run/l5-c1b/chain6/summary.txt`);
  the a815678 measurement was left to finish (`measure-summary-a815678.txt`).
- 8f0a5a2: synthetic-store unit tests 5 passed (fail-first 2 / 3 on the a815678 snapshot); the API
  module collects 16 tests; lint OK; typecheck OK.
- 8f0a5a2 measurement (`measure-summary-8f0a5a2.txt`): ten keys 10/10; 192 selection 192/192; all
  active 203 / 38 / 2, zero new failures, 20 turned green; engine + architecture + unit 1,586 passed
  / 5 xfailed; properties OK; END OK 16:11:24. Chain 7 (`gates-chain-7.sh`, PID 47178, START
  16:00:22 head 8f0a5a2, launched by `relaunch-after-measure-2.sh`) had not claimed and was stopped
  by the lane by exact PID before SSP-ADMISSION-R1 (b) changed the head (`chain7/summary.txt`).
- 021a067, 053813f: §3.8 gates.
- 053813f measurement (`measure-summary.txt`, START 16:19:00): ten keys 10/10; 192 selection
  192/192; all active 203 / 38 / 2, zero new failures, 20 turned green; engine + architecture + unit
  1,586 passed / 5 xfailed; properties OK; END OK 16:30:42.
- Chain 8 (`gates-chain-8.sh`, PID 92665, START 16:19:02 head 053813f, launched by
  `relaunch-after-measure-3.sh`) passed MEASURE-OK and took the l5 lock at 16:31:03 but held no
  global slot and ran no stage; the supervisor's ordering condition (no global claim before the
  interim main batch 17243 has claimed one) could not be taken in place, so the lane stopped it by
  exact PID at 16:47:04; its EXIT trap released the lock (LOCK-RELEASED 16:47:37;
  `chain8/summary.txt`, whose earlier STOPPED line was a failed precondition check, as its NOTE
  says).
- Chain 9 (`.run/l5-c1b/gates-chain-9.sh`, an immutable copy of chain 8 plus the condition; PID
  63635, START 16:48:01 head 053813f, dirty = this record): MEASURE-OK, NOT-BEFORE passed, l5 lock
  taken 16:48:01; polls `~/dev/erev/.run/supervisor/main-gates/run-8d76fea/summary.txt` read-only
  every 30 s for a "claimed" line, then the normal claim rules → parity filtered, parity, test-pg,
  ci → one trap releases lock and slot as owner only; results below as they land.
- Chain 9 results: parity filtered OK 121 / 121; parity 121 / 122 (deferred GPB-3); test-pg 289 / 1
  (enum count); ci FAIL 2,610 / 50 / 5 skipped (46 min); END 18:06:31 head 053813f dirty 1 (this
  record); LOCK-RELEASED and slot 1 RELEASED 18:06:31 by the chain's own trap. Diagnosis and the
  fixes in §6.3.
- 18:20–18:39: ci-fix commit prepared — test-support and test-only changes (§6.3 causes 1–3), `make
  lint` OK, targeted DB runs A2 / B / C2 / C3 / D2 all green (§6.3 table); committed inside the lint
  guard as the next commit after 053813f; `measure.sh` (CPU) re-run on that head follows.
- 18:39: ci-fix commit d80c124. 18:42:34–18:55:14: `measure.sh` on d80c124 END OK (§6.4). Waiting
  for the P2 merge → 0056 → 0055 re-parent → the single DB chain on the final head.

GATE-BIND-1: the chain is the lane's progress and merge evidence; release evidence is produced on
main. The chain script implements the 12:16 amendment and the 13:38 clarification: mkdir-atomic
`gate-slot-N.d` claim with owner PID + `ps lstart`, the flat file written second for readers,
liveness by PID + start time with UNKNOWN treated as held, stale cleanup only for a provably dead
owner, release only of its own claim (`rm -r` directory + flat file), and before every DB stage a
per-runner count of the other worktrees' `gate_report.py ci` / `test-pg`, `support.parity.report`
and explicit `-m pg` pytest processes (children under a `gate_report.py` ancestor are that runner's
own) plus the other slot claim, proceeding only at ≤ 1 other running stage and ≤ 1 other claim;
`make properties` is DB-free and runs outside the chain; nothing is killed.
- 2026-09-20: re-parent preparation applied branch-locally (§8): renumbers 1.41 / 1.26 / 1.32, 03 provisional 1.6, E-125 → E-131 sweep, drift pins; statuses in `.run/l5-c1b/statuses-reparent.log`; committed; main not merged (frozen).
- 2026-09-20 02:4x–03:0x: main c60529ab merged (§9), migration held out, privacy catalogue row for `quantity_unit`, statuses captured; committed; then main 065e7f65 (wave end) merged on top (§9, second block).
- 2026-09-20 08:0x–08:3x: main 05c30117 merged (§10), 0060 on 0059 restored with both pins, statuses captured, interim head committed; holding for the final small re-merge (main d3166d0a + F-CTR / ENG-C8).
- 2026-09-20 09:1x–09:3x: main 30e9709f merged (§11), statuses all rc=0, READY reported.
- 2026-09-20 10:4x–11:0x: main d3a89805 merged (§11.1), statuses all rc=0, READY re-reported with the exact head.
