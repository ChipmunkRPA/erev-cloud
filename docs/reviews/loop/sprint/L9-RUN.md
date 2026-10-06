# L9-RUN: answer-key runner contract attribution, Level 9 remediation

Lane builder record for lane L9-RUN (answer-key runner) on `sprint/l5` (worktree `~/dev/erev-wt/l5`). Binding: `docs/01-DECISIONS.md` D-90 ("RND-CHK-003C golden representation erratum"; "RET-BR-03 answer-key runner contract attribution"), dev-guide §9.5.6 rev 1.5 (subledger block `contract`), and verification record `~/dev/erev/.run/l9/verify-findings.json` finding `f3-ret-br-03` (investigation, reproduction and blast-radius verifiers, prototype `proto/attribution.py`).

## Start

- STEP 0: clean tree; `git merge --ff-only main` to 889eb63 (D-90); `make setup` OK.
- Baseline at 889eb63: `test_assert_checkpoints.py` + `test_runner_engine.py` 45 passed, 1 failed (`test_d85_key_implied_price_change_settlement`: the key at 889eb63 is regenerated and the note reads `cr 33.34`, while the test expects `cr 100.00`). `make answer-keys ID=RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION`: failed, 10 subledger mismatches (March 2,000.00; May 12,000.00; June 12,000.00 and 1,600.00; August 400.00), as the investigation found.
- Retry after the API outage (2026-09-17): adopted 9df7678 and faf425a and this untracked record; no uncommitted source change. The earlier `make ci` (PID 77831) had exited (`kill -0 77831` fails); its report `.run/reports/ci/report.json` is build faf425a, exit 0. Gate slot `gate-slot-1` (owner `L9-RUN ci 77831`) removed. No sync with main.

## Changes

### D-90 RND-CHK-003C (9df7678)

- `test_runner_engine.py::test_d85_key_implied_price_change_settlement`: the docstring now lists the per-obligation REFUND_LIABILITY credits (POB-001 Cr 33.34, POB-002 Cr 33.33, POB-003 Cr 33.33; total 100.00). The expected run note ends `REFUND_LIABILITY cr 33.34 (JET-05c)`, the first credit line (D-85 run note).
- No runner change: `_implied_settlements` already quotes the first credit line of the key.

### D-90 RET-BR-03 (faf425a)

`backend/tests/support/answer_keys/runners.py`:
- `_intent_contract(intent, group_key, members)`: the `contract_key` every line carries, else None. Attribution fails closed when:
  - the lines disagree, or only some lines, or none, carry the value;
  - the value is not a member of the intent's combination group;
  - a contract named by the subject differs from the value.
- `_named_contracts(subject_key, group_key, members)` lists the contracts a subject names. It splits on the encoded CV-21 delimiters, then decodes:
  - `<contract>/<…>` (obligation, estimate element, cost asset, recognition component) names its leading component;
  - `<name>@<entity>` names `<name>`, unless that is the group code and not a member;
  - a component key `<group>@<entity>/<KIND>/<source>` names the source's leading component, plus its head when the head is not the group code. (Review finding below: the first source component only.)
- `_CheckpointComparison`:
  - `group_books` holds each checkpoint book (outputs, then close passes) with its `GroupInput`. It replaces `book_outputs` and `pass_books`, which had no other callers.
  - `block_intents(block)` returns the intents of the block's period and entity plus the unattributable ones. With `contract` set it reads only the books of that contract's combination group.
  - `net(block, intents, with_kind)` holds the unchanged DG-AK-56 summation.
  - `aggregate(block, with_kind)` keeps its signature and records nothing.
  - `subledger()` reports each unattributable intent once per (period, entity, contract, entry key). Subject `subledger <period> <entity> <contract> entry <entry key> <subject key>`, field `contract`, expected the block contract, actual `<unattributed>` (`UNATTRIBUTED`).
- Unfiltered blocks: same intents, same order (outputs then passes), same sums. `runner: platform` keys never reach the comparison (`assert_checkpoints` raises `PLATFORM_RUNNER_MISSING`).
- `_subject_parts` is unchanged; `_line_obligation`, `exceptions()` and `blocking_findings()` still use it (L9-RUN-Q-1).

### D-90 RET-BR-03 review fix (6511ce3): refund component source grammar

Review finding (independent review of faf425a; verified): `_named_contracts` validated only the first component of a refund component source. A real CONCESSION source is `f"{ev.event_key}/{subject_key}"` (refund_liability.py `_concessions`), a global event key followed by an obligation subject key, so `G@US01/CONCESSION/C-A/EV-000009/C-B/POB-001` with every line `contract_key` C-A named only C-A and was attributed to C-A although the subject names C-B. Verified on faf425a: `test_subledger_contract_filter_concession_conflicting_subject_fails_closed` counts the entry in C-ENT-A's blocks (below). The faf425a fixtures used a non-engine CONCESSION shape `<contract>/EV-<n>/<obligation>`, which hid the gap.

Grammar table (refund_liability.py; every `_key(...)` call and `source_key` construction). `_key` is `f"{st.group_code}@{entity}/{kind}/{source_key}"`; the JET-04b, credit-memo consumption and remeasurement targets take `subject_key=component.key` (lines 339, 538, 563, 698, 734), so each posting intent subject is the component key. `<c>`, `<obligation>`, `<element>` and `<entity>` are CV-21 encoded components (`(?:[^%/@#:]|%(?:2F|40|23|3A|25))+`); `EV-<n>` is the CV-22 serial `EV-` and 6 or more digits (`:06d`, bundles.py `event_key`, runners.py).

| Kind | Producer and `_key` call | `source_key` | Source grammar | Contracts named |
|---|---|---|---|---|
| TERMINATION | `_terminations`: `_key(st, entity, TERMINATION, ev.event_key)` | the `CONTRACT_TERMINATED` global event key | `<c>/EV-<n>` | `<c>` |
| CONCESSION | `_concessions`: `source_key = f"{ev.event_key}/{subject_key}"`; `_key(st, ob.contracting_entity, CONCESSION, source_key)` | the `_concession_event` boundary event key, then the refund-quota obligation subject key | `<c1>/EV-<n>/<c2>/<obligation>`, or `<c1>/EV-<n>/<c2>@<entity>` | `<c1>` and `<c2>` |
| VARIABLE_CONSIDERATION | `measure`: `_key(st, entity, VARIABLE_CONSIDERATION, estimate_key)` | the estimate key `obligation_subject_key(contract, element_code)` (bundles.py; runners.py) | `<c>/<element>` | `<c>` |
| RETURN | `measure`: `_key(st, ob.contracting_entity, RETURN, subject_key)` over `recognition.return_states` | the obligation subject key `obligation_subject_key(contract, obligation)` | `<c>/<obligation>` | `<c>` |
| UNCLAIMED_PROPERTY | none (ENC-8, post-rc; L2-4-Q-16) | none | none | fails closed (L9-RUN-Q-6) |
| any other kind | none | none | none | fails closed |

Head: `<name>@<entity>` with both parts encoded components; `<name>` equal to the group code names nothing, otherwise it names a contract (faf425a semantics). A head or source outside its grammar names nothing attributable and the intent fails closed.

`backend/tests/support/answer_keys/runners.py`:
- `_source_contracts(kind, source)`: the source split on `/` before any decoding; returns the contracts of the kind's grammar, else None.
- `_named_contracts` returns None for a component key whose head is not `<name>@<entity>` or whose source does not match its kind; `_intent_contract` returns None when `_named_contracts` does.
- Constants `RETURN_COMPONENT`, `VC_COMPONENT`, `TERMINATION_COMPONENT`, `CONCESSION_COMPONENT` (the key form is matched, not imported), `_ENCODED_COMPONENT`, `_EVENT_SERIAL`.
- Non-component subjects (`<contract>/<…>`, `<name>@<entity>`) are unchanged.

`backend/tests/unit/answer_keys/test_assert_checkpoints.py`:
- Fixtures corrected to the engine CONCESSION shape `<c>/EV-<n>/<c>/<obligation>`: `test_subledger_contract_filter_keeps_refund_component_entries[CONCESSION…]`, `test_intent_contract_decodes_cv21_delimiters`, `test_subledger_unfiltered_totals_unchanged`.
- New:
  - `test_subledger_contract_filter_concession_conflicting_subject_fails_closed`: G-ENT-01, subject `G-ENT-01@US01/CONCESSION/C-ENT-A/EV-000009/C-ENT-B/POB-B`, lines C-ENT-A; blocks C-ENT-A (role), C-ENT-A (role_account), C-ENT-B. Expected exactly one `contract` mismatch per contract.
  - `test_subledger_contract_filter_same_contract_concession_attributed`: `…/CONCESSION/C-ENT-A/EV-000009/C-ENT-A/POB-A` counts in C-ENT-A's block (Dr 7.00 / Cr 7.00) and in no other.
  - `test_intent_contract_concession_encoded_contracts_split_before_decoding`: the raw id `C/1@A#B:%` encoded in both positions (obligation and `@<entity>` subjects) is attributed; C-2 in either position, or the encoded `C%2F1`, fails closed; a member `C-2/EV-000009/C-2` encoded in both positions is attributed; `C-2%2FEV-000009%2FC-2/POB-1` (decoded first, a concession naming C-2 twice) fails closed.
  - `test_intent_contract_refund_component_grammar_names_its_contracts`: the engine shape of each kind attributes to the named member and not to the other (incl. a 7-digit serial and the `@<entity>` concession subject).
  - `test_intent_contract_refund_component_outside_its_grammar_fails_closed` (22 cases, adversarial self-check below).

Adversarial self-check (step 4): one or more counterexamples per kind; every one reached acceptance on faf425a (fail-first log) and fails closed at 6511ce3.

| Kind | Counterexamples (group G, members C-A and C-B, lines C-A) |
|---|---|
| RETURN | `…/RETURN/C-A/POB-001/C-B` (extra component); `…/RETURN/C-A` (no obligation); `…/RETURN/C-A#FIXED/POB-001` (raw `#`); `…/RETURN/C-A/POB:001` (raw `:`); `…/RETURN/C-A/POB%2G` (malformed escape); `G@US01/RETURN` (no source) |
| VARIABLE_CONSIDERATION | `…/VARIABLE_CONSIDERATION/C-A/VC-001/C-B/VC-002`; `…/VARIABLE_CONSIDERATION/C-A` |
| TERMINATION | `…/TERMINATION/C-A/EV-000009/C-B/POB-001`; `…/TERMINATION/C-A/POB-001` (no event serial); `…/TERMINATION/C-A/EV-9` (5 digits short) |
| CONCESSION | `…/CONCESSION/C-A/EV-000009/C-B/POB-001` (review); `…/C-A/EV-000009/C-B@US01`; `…/C-A/EV-000009/C-A` (truncated subject); `…/C-A/POB-001/C-A/POB-001` (no event key); `…/C-A/EV-000009/C-A/POB-001/C-B` (extra); `…/C-A/EV-000009/C-A@US01@C-B` (raw `@` in the entity) |
| UNCLAIMED_PROPERTY, other | `…/UNCLAIMED_PROPERTY/C-A/POB-001`; `…/OTHER/C-A/POB-001` |
| Head | `G@US01#X/RETURN/C-A/POB-001`; `G@US01@C-B/RETURN/C-A/POB-001`; `G@/RETURN/C-A/POB-001` |

A head naming the owner contract (`C-A@US01/RETURN/C-A/POB-001` in group G) still attributes: every contract it names is the owner, as faf425a.

## Tests and fail-first proof

`git stash` is forbidden, so the proofs run on scratch overlays under `.run/l9-run/`.

faf425a batch:
- `overlay-old` has symlinks to every `backend/tests/support` module except `answer_keys/runners.py`, which is the byte copy of the 889eb63 runner. The overlay appends one shim, `_intent_contract = _subject_parts(subject_key)[0]`, which is the old attribution. It exists only so the new test module imports.
- The new test files run against it (`PYTHONPATH=overlay-old`, `-c backend/pyproject.toml`).
- `overlay-new` is the same with the committed runner, as a control.

Results:
- Old runner: 15 failed, 46 passed (`fail-first-old.log`). The 15 failures are exactly the new tests; the 46 passes are the 45 existing tests plus `test_d85` with its new expectation.
- Control on the new runner: 61 passed (`fail-first-new-control.log`).

| New test | Failure on the old runner |
|---|---|
| `test_subledger_contract_filter_keeps_refund_component_entries[RETURN, VARIABLE_CONSIDERATION, TERMINATION, CONCESSION]` (4) | dr and cr `<absent>` (the head `CG-C-RND-1@US01` drops the JET-04b entry) |
| `test_subledger_contract_filter_combined_group` | A and B entries `<absent>` (head `G-ENT-01@US01`); no `contract` mismatch for the undimensioned entry |
| `test_subledger_contract_filter_group_code_equal_to_member_id` | `<absent>` lines instead of the two `contract` mismatches of the misattributed entry |
| `test_subledger_contract_filter_non_member_head_in_singleton_group[C-OTHER/POB-001, C-OTHER@US01, {group}@US01/RETURN/C-OTHER/POB-001, CG-C-OTHER@US01/RETURN/C-RND-1/POB-001]` (4) | `[]`: dropped silently, no mismatch |
| `test_subledger_contract_filter_group_at_entity_fx_remeasurement` | functional-only FX lines `<absent>` in the singleton member's block |
| `test_subledger_contract_filter_mixed_and_missing_dimensions_fail_closed` | `aggregate()` keeps all three entries (head `C-RND-1`) |
| `test_intent_contract_decodes_cv21_delimiters` | `'G/1@US01' == 'C/1@A#B:%'` for the encoded component key |
| `test_subledger_unfiltered_totals_unchanged` | filtered totals 40.09, not 70.21 (only `C-RND-1/…` and `C-RND-1@…` subjects kept; the unfiltered half passes on both runners by design) |
| `test_runner_engine.py::test_l9_ret_br_03_contract_blocks_include_jet_04b` | `{REVENUE/4000: 12000, CONTRACT_LIABILITY/2100: -12000}` instead of `{REFUND_LIABILITY/2110: -12000, REVENUE/4000: 12000}` |
| `test_d85_key_implied_price_change_settlement` (expectation change) | at 889eb63 the old expectation `cr 100.00` fails against the regenerated key; the new one passes on both runners |

Review-fix batch (6511ce3):
- `overlay-faf425a`: symlinks to every `backend/tests/support` module; `answer_keys/runners.py` is `git show faf425a:…` (cmp-identical to the tree before the fix); the working-tree `test_assert_checkpoints.py` copied beside it. `support.answer_keys.runners.__file__` resolves to the overlay copy. No shim.
- faf425a runner: 24 failed, 26 passed (`fail-first-faf425a.log`). Failures: the conflicting-subject test, the encoded-contracts test (first failing assertion: `owner('C%2F1%40A%23B%3A%25/EV-000009/C-2/POB-1')` returned `'C/1@A#B:%'`), and the 22 grammar cases (each returned `'C-A'`). Passes: the 24 faf425a tests with the corrected fixtures, the same-contract concession test and the grammar-names test (acceptance cases faf425a already accepts).
- The conflicting-subject test on faf425a (`fail-first-faf425a-conflict.log`): four `line <absent>` mismatches in C-ENT-A's two blocks (`CONTRACT_LIABILITY dr 7.00`, `REFUND_LIABILITY cr 7.00`, each twice), nothing in C-ENT-B's block and no `contract` mismatch: the entry was misattributed to C-ENT-A.
- Control at 6511ce3: 50 passed (`units-fix-assert.log`).

Engine subject census (`.run/l9-run/grammar_sweep.py`, `grammar-sweep.txt`): one engine run per active engine key; every posting intent of every checkpoint and close-pass book, compared by the faf425a runner (byte copy) and the 6511ce3 runner. 232 active, 227 engine, 42 raise in the engine before comparison, 16,539 posting intents. Component-form subjects: RETURN `<c>/<x>` 238, VARIABLE_CONSIDERATION `<c>/<x>` 34, TERMINATION `<c>/EV-<n>` 6, CONCESSION `<c>/EV-<n>/<c>/<x>` 2 (VC-CHK-113-TC-POBVC-16: `CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232`). No other component-form shape. Unparsed by the 6511ce3 runner: 0. Concessions naming two contracts: 0. Intents attributed differently: 0. `assert_checkpoints` passed 173 on both runners; no key's mismatch list changed.

## Counts

At faf425a:
- `make test TESTS=backend/tests/unit/answer_keys/test_assert_checkpoints.py`: 24 passed (10 existing, 14 new).
- `make test TESTS=backend/tests/unit/answer_keys/test_runner_engine.py`: 37 passed (36 existing, 1 new).
- `make answer-keys ID=RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION`: 1 passed (before: failed, 10 mismatches).
- `make answer-keys ID=RND-CHK-003C`: 1 passed.
- Release-gate selection (`rg-selection.txt`, 173 ids): 172 of 173 passed. The only failure is `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION` (12 mismatches, pending D-90a). Main was 170 of 174 (MOD-JS-06, ONB-CHK-121, RET-BR-03, RND-CHK-003C); without ONB-CHK-121 that is 170 of 173. RET-BR-03 now passes through this runner change, RND-CHK-003C through the 889eb63 key regeneration. No new failure.
- `make answer-keys` (all active): 173 of 232 passed, 59 failed, 2 withdrawn. Main was 171 of 232; the +2 are RET-BR-03 and RND-CHK-003C.
- Runner-only comparison (`.run/l9-run/before_after.py`, `before-after.txt`): one engine run per active engine key, compared by the 889eb63 runner (byte copy) and by the committed runner. 232 active, 227 engine, 42 raise in the engine before comparison, passed 172 before and 173 after. Changed: RET-BR-03 only (10 to 0 mismatches). No other key's mismatch list changes.
- `make parity K="not point_in_time_equivalence"`: 121 of 121.

At 6511ce3 (reports carry `worktree_dirty: true` for this untracked record only):
- `make test TESTS=backend/tests/unit/answer_keys/test_assert_checkpoints.py`: 50 passed (24 faf425a, 26 new).
- `make test TESTS=backend/tests/unit/answer_keys/test_runner_engine.py`: 37 passed.
- `make answer-keys ID=RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION`: 1 passed.
- `make answer-keys ID=RND-CHK-003C`: 1 passed.
- Release-gate selection (173 ids): 172 of 173 passed; failing: `MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION` (12 mismatches, pending D-90a). Same failing set and mismatch counts as faf425a.
- `make answer-keys` (all active): 173 of 232 passed, 59 failed, 2 withdrawn. Same failing set and per-key mismatch counts as faf425a (`fix-ak-all.json` against `ak-all.json`).
- `make parity K="not point_in_time_equivalence"`: 121 of 121.

## Gates

| Gate | faf425a | 6511ce3 |
|---|---|---|
| `make lint` | OK | OK |
| `make typecheck` | OK (558 source files) | OK (558 source files) |
| `make parity K="not point_in_time_equivalence"` | OK: 121 of 121 | OK: 121 of 121 |
| `make answer-keys` selection (173 ids) | 172 passed, 1 failed (MOD-JS-06, pending D-90a) | 172 passed, 1 failed (MOD-JS-06, pending D-90a) |
| `make answer-keys` all active | 173 of 232, 59 failed (main 171) | 173 of 232, 59 failed |
| `make ci` | OK: backend 2158 passed, 0 failed, 0 skipped; vitest 602 passed, 0 failed, 0 skipped | OK: backend 2184 passed, 0 failed, 0 skipped (2158 + 26 new); vitest 602 passed, 0 failed, 0 skipped |
| `make test-pg` | OK: backend 290 passed, 0 failed, 0 skipped | OK: backend 290 passed, 0 failed, 0 skipped (third run; see Deviations) |

## Deviations

- The prototype's fallbacks for undimensioned entries (the member named by the subject head, else the sole member of a singleton group) are not built. D-90 requires every line to carry `contract_key`, so missing dimensions fail closed. The engine sets the value on every line of a singleton group (assign.py every-member fallback), so no corpus comparison changes.
- The mismatch subject adds `entry <entry key>` to the investigation's `<subject key>`, so distinct entries on one subject never render as duplicate rows.
- Scope, as the blast-radius verifier measured: the attribution also admits group@entity FX_REMEASUREMENT entries and TERMINATION and CONCESSION component entries into contract-filtered blocks. No corpus key compares them today (runner-only comparison above).
- Commit order: the RND-CHK-003C expectation (9df7678) was committed from an intermediate file state holding only that hunk (no partial staging); faf425a restored the full file.
- Review fix: three faf425a fixtures carried the non-engine CONCESSION shape `<c>/EV-<n>/<obligation>`; under the grammar it fails closed, so they now carry the engine shape. No expected value changes.
- Review fix: the CONCESSION grammar also accepts the subject form `<c>@<entity>` named in the review brief, although `_concessions` produces only obligation subjects (any other quota key raises the S06-R-09 invariant). Both contracts are still validated.
- Review fix: the event serial accepts 6 or more digits (`:06d`); CV-22 reads 6 digits.
- `make test-pg` at 6511ce3 ran three times. Attempt 1 (launched beside the answer-key, parity and lint chains) and attempt 2 (while this lane's `make ci` test stage ran) errored in session setup: 2 passed, 288 errors, `LockNotAvailable: canceling statement due to lock timeout` on `pg_advisory_lock`, the DG-TST-11 serialisation lock of `test_database` (`fix-test-pg-attempt1.log`, `fix-test-pg2.log`). A read-only `pg_locks` query after attempt 2 found the holder: this worktree's `make ci` pytest session on `erev_rv_l5_test`, holding since 00:35:25Z. Attempt 1's holder was not captured. Lock timeout is not one of the listed rerun causes, and no test reached an assertion. Attempt 3 ran alone after `make ci` exited: 290 passed (`fix-test-pg3.log`).

## Spec questions

- **L9-RUN-Q-1 (exceptions attribution).** `exceptions()` and `blocking_findings()` still match an exception row's `contract` with the `_subject_parts` head. A finding whose subject is a refund component key or `<group>@<entity>` yields `CG-<contract>@<entity>` or the group code there, so a row naming the contract cannot match it. No current key is affected. Should the §9.5.6 `exceptions` row adopt the D-90 attribution (findings carry no line dimensions, so by the named contract only), or stay as built?
- **L9-RUN-Q-2 (group code equal to a member id).** For `<name>@<entity>` with `combination_group` equal to a member id, the subject is ambiguous (contract and entity, or group and entity). The runner reads the member, and engine `assign.subject_contracts` also resolves it to that member, so a group-level entry in such a group is attributed to that member without detection. No corpus key has such a group. Should the loader reject a `combination_group` equal to a contract external id (post-rc)?
- **L9-RUN-Q-3 (raw group code in component keys).** `refund_liability._key` builds `<group>@<entity>/<KIND>/<source>` from the raw `st.group_code`, while stages 05 and 07 encode the group code (CV-21). A group code with `/`, `@` or `#` breaks the key shape; the runner then fails closed. Owner and timing (stage 10, post-rc)?
- **L9-RUN-Q-4 (multi-member groups).** Stage 14 sets no `contract_key` on component keys or `<group>@<entity>` subjects of a multi-member group (`assign.subject_contracts` returns every member). A contract-filtered block on such a group therefore reports those entries `<unattributed>` until the engine resolves `RefundComponent.contract_key`. Owner and timing of that stage 14 follow-up (post-rc)?
- **L9-RUN-Q-5 (reported once).** An unattributable entry is reported once per (period, entity, contract, entry key). In a multi-member group it appears once in each member's block, because the subjects name different contracts; two blocks of the same contract, period and entity report it once. Does that reading of "never reported twice" stand?
- **L9-RUN-Q-6 (UNCLAIMED_PROPERTY grammar).** The kind has no producer (ENC-8, post-rc), so the runner has no source grammar for it and fails closed on any such component key. When stage 09 publishes escheat components, their source grammar must join `_source_contracts`. Owner: the ENC-8 lane (post-rc)?
- **L9-RUN-Q-7 (cross-member concession boundary).** `_concession_event` takes a boundary event from the obligation's segments without checking the event's contract. If a combined group can date a member's concession from another member's event, the CONCESSION source names two contracts and a contract-filtered block reports the entry `<unattributed>` (D-90 fail closed). The census measured none (2 CONCESSION intents, both one contract). Is such a boundary possible by ENGINE_SPEC_B S10-R-13, and if so which contract owns the entry?
- **L9-RUN-Q-8 (encoded estimate head).** `refund_liability.measure` looks up `contracts.get(estimate_key.rsplit("/", 1)[0])`: the encoded estimate head against raw external ids. A contract id holding a CV-21 delimiter therefore yields no VARIABLE_CONSIDERATION component (skipped as portfolio-scoped). `_terminations` and the VC component also set `subject_key` from the raw id. No corpus key has such an id. Owner and timing (stage 10, post-rc)?

## Shared files touched

- `backend/tests/support/answer_keys/runners.py`: `_named_contracts`, `_intent_contract`, `UNATTRIBUTED`, `_CheckpointComparison.group_books`, `unattributed`, `subledger`, `aggregate`, `block_intents`, `net` (faf425a); `_source_contracts`, `_named_contracts`, `_intent_contract`, `RETURN_COMPONENT`, `VC_COMPONENT`, `TERMINATION_COMPONENT`, `CONCESSION_COMPONENT`, `_ENCODED_COMPONENT`, `_EVENT_SERIAL` (6511ce3).
- `backend/tests/unit/answer_keys/test_assert_checkpoints.py`: `_line` (`contract_key`) and `_intent` (`subject_key`, `entry_kind`) keyword parameters; D-90 helpers and 14 tests (faf425a); three CONCESSION fixtures and 5 tests (26 cases) (6511ce3).
- `backend/tests/unit/answer_keys/test_runner_engine.py`: `test_d85` docstring and note; `test_l9_ret_br_03_contract_blocks_include_jet_04b`.
- No engine, answer key, golden file or other document change.

Commits: 9df7678 (RND-CHK-003C expectation), faf425a (runner attribution and tests), 6511ce3 (review fix: refund component source grammar); this evidence with the batch.
