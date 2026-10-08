# RPO realized-fee counterexamples — October 8, 2026

Measured on clean revision `7c83cb4a994157c51f0d8cd86d860d6acc253cc3`.
This baseline is diagnostic evidence, not a release acceptance result. The engine repair
and its validation are recorded below; the API report and remaining release checks stay open.
No accounting treatment or expected result was changed.

## Inputs and observed results

Used the existing stage-09 deterministic-component fixtures: a January–December 2026 usage
obligation, MONTHLY_EVEN fixed-fee recognition, and USD 150 usage reported March 31 for March.
The real stage-09 recognition calculation and real stage-15 `rpo.rollforward` consumed the same
allocated state. The fixture constructs allocation inputs directly; this is not a full API or
all-stage bundle run. Stage-09 trace reevaluation and its allocation identity passed.

| Fixed fee | Stage-09 March allocation | Revenue to March | Stage-09 remaining | Stage-15 March opening | March revenue line | Stage-15 closing | Unexplained |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 150.00 | 150.00 | 0.00 | 0.00 | -150.00 | 0.00 | 150.00 |
| 12,000.00 | 12,150.00 | 3,150.00 | 9,000.00 | 10,000.00 | -1,150.00 | 8,850.00 | 0.00 |

The pure-usage case reproduces B4-2. The mixed fixed/usage case adds a more serious finding:
the engine rollforward closing is understated by 150.00 while its unexplained line is zero.
A zero arithmetic difference therefore does not establish a correct closing balance.
This measurement concerns the engine rollforward; it does not establish that the API report
produces the same closing error. The API report's documented cause-classification gap remains.

## Code paths and repair scope

- Stage 09 `schedule._realised_at` includes PERIOD_VC and ROYALTY amounts in allocation.
- Stage 15 `rpo.rollforward` selects FIXED segments; `_rpo_at` subtracts total recognized
  revenue from that fixed allocation, and `_movements` assigns fixed-segment changes by cause.
- The API report builder separately classifies stored allocation changes by contract-event
  cause. Fixing only that map cannot repair the engine's independently wrong closing balance.

The repair needs a shared dated realization measure, an explicit addition classification, and
independent closing assertions. Cover pure/mixed usage, royalties with guarantees and delayed
satisfaction, recognition holds, corrections, cancellations, Step-1 exclusion/entry, practical
expedients and differing performing/contracting calendars. Preserve actual unexplained amounts;
do not plug the arithmetic remainder into an addition line. Verify the API report against the
corrected engine and existing allocation/revenue invariants, then include the change in the
pending engine release cut and replays.

## Reproduction

Run from the repository with the locked backend environment:

```python
import runpy
from datetime import date
from erev_engine.stages.s15_disclosures.rpo import rollforward

m = runpy.run_path(
    "backend/tests/engine/s09_recognition/test_s09_deterministic_component.py"
)
for fee in (0, 12000):
    report = m["_usage_report"](2, m["MARCH_31"], date(2026, 3, 1), "150.00")
    allocated = m["allocated_state"]([m["_usage"](fee)], events=[report])
    recognition, trace = m["_run"](allocated)
    result = rollforward(m["CTX"], allocated, recognition, "US01", "FY2026-P03")
    print(fee, m["_split"](recognition), dict(result.lines))
```

Use `PYTHONPATH=backend:backend/tests backend/.venv/bin/python`.
Printed amounts are minor units except the input fixed fee.
Local log: `/private/tmp/erev-rpo-usage-diagnostic-2026-10-08.log`.
SHA-256: `0f2c4c10319ba8f09f9ae2d30131e4c0aa3660276835272790cfc3c63f1213e9`.

## Engine repair and scoped verification

The engine now uses the recognition stage's shared `schedule.realised_at` calculation for
PERIOD_VC and ROYALTY allocation at the same performing-entity period dates as revenue.
Closing allocation includes those amounts; their period changes appear on VC_ESTIMATE_CHANGES.
An amount already included on a Step-1 entry is not added twice. Entirely excluded contracts
carry no realized RPO activity. Cancellation remainder calculation includes realized allocation.
The implementation uses source-derived amounts, never the unexplained difference as a plug.

The original two usage regressions failed in 0.23 seconds. After repair, the disclosure suite
and existing deterministic-component tests passed (77 tests, 19.29 seconds). Added royalties
with a minimum guarantee, both satisfied and awaiting satisfaction, and a downward statement
correction: 13 royalty-module tests passed in 0.26 seconds. The broader recognition/disclosure
and import-cycle/forbidden-pattern run passed **268 tests in 79.77 seconds**. Six focused usage,
recognition-hold and Step-1 entry/exclusion checks then passed in 0.24 seconds. Source Mypy,
Ruff lint/format and whitespace checks passed.

The mixed usage case now closes at 9,000.00; both usage cases record the 150.00 addition and
zero unexplained difference. Held usage stays in remaining allocation instead of disappearing.
Royalty additions net the existing guarantee and retain unrecognized royalties until satisfaction;
negative corrections reverse additions. Existing fixed-only cancellation and exemption regressions
also passed, but the complete combined-edge matrix listed above and API report verification
remain outstanding. This does not resolve B4-2 as a whole or claim full release readiness.
The disclosure change joins the pending 0.3.0 to 0.4.0 cut and candidate replay requirements.

Local logs: `/private/tmp/rpo-realised-baseline.log`, `/private/tmp/rpo-realised-fixed.log`,
`/private/tmp/rpo-royalty-fixed.log`, `/private/tmp/rpo-realised-expanded.log` and
`/private/tmp/rpo-realised-entry.log`. No deployment or historical output rewrite occurred.

## API report attribution repair

The report builder now recognizes USAGE_REPORTED, including royalty statements, as variable
consideration activity. It tests whether an obligation existed in the previous version instead
of treating a zero previous allocation as a new contract. Unknown causes remain unexplained.
Where one version carries competing allocation cause classes, it now also leaves the delta
unexplained rather than choosing the alphabetically first event. Full per-cause decomposition
of a multi-event version remains outstanding.

The unit baseline had three failures and one pass in 0.43 seconds. A PostgreSQL report test
first stopped at input validation because the test sent rated_amount as a scalar; correcting
it to the API Money object produced the actual baseline failure: **one failed in 11.49 seconds**,
with VC_ESTIMATE_CHANGES at 0.00 instead of 150.00.

After the repair, the unit chain suite passed 18 tests in 0.40 seconds. The expanded database
RPO/disaggregation and unit chain suites passed **32 tests in 61.81 seconds**. The API case
submits the usage event with evidence and independent approval, then runs the report. It asserts
no new-contract amount, a 150.00 variable-consideration addition, unchanged opening and closing
RPO, revenue lower by 150.00 on the rollforward, zero unexplained and both report tie-outs PASS.
The unit cases cover zero/nonzero opening allocations and unknown/competing causes. Mypy,
Ruff lint/format and whitespace checks pass. No expected accounting oracle was weakened.

Logs: `/private/tmp/rpo-api-zero-baseline.log`, `/private/tmp/rpo-api-usage-baseline-valid.log`,
`/private/tmp/rpo-api-unit-fixed.log`, `/private/tmp/rpo-api-expanded.log`.

B4-2 remains partially open. Further verification and implementation must cover one first
version containing later realized-fee events, per-cause decomposition of batched changes,
royalties through the API, and the combined lifecycle/exemption/calendar matrix. These results
prove the measured later-version path, not every report shape or the whole release.


## First-computation timing counterexample — October 8, 2026

On published f3c48c4, defer the fixture's initial computation, then submit and independently
approve K08/O1 USAGE_REPORTED for March 1–31 with effective date March 31, quantity 1500
and rated_amount USD 150.00. The first calculation includes activation and this usage together.
January's report states NEW_CONTRACTS 80,150.00 rather than the fixed 80,000.00. The new local
regression also checks January closing against independently posted ledger revenue and requires
March VC_ESTIMATE_CHANGES 150, no new-contract addition, no unexplained amount and both tie-outs.
Baseline: one failure in 11.20 seconds, `/private/tmp/rpo-first-calculation-baseline.log`.

A pending local repair emits `realised_allocation` at every revenue period and at version date,
including explicit zero points, using the existing recognition realization calculation. It keeps
realization independent of recognized revenue (holds and royalty satisfaction can separate them).
The dated reader adjusts allocation and remainder by the stored-versus-dated realization delta;
the RPO builder separates fixed-allocation changes from realized-fee changes. These edits are
**uncommitted and incomplete**, not evidence that published main has this repair.

Local checks completed:

- Recognition, disclosures and trace/formula suites: 262 passed in 96.04 seconds,
  `/private/tmp/rpo-realised-trace-expanded.log`.
- Dated reader and RPO version-chain units: 79 passed in 0.97 seconds,
  `/private/tmp/rpo-realised-reader-units.log`.
- API timing/entry/late-event suite: five passed, one failed in 35.29 seconds,
  `/private/tmp/rpo-realised-reader-api.log`. The new case now reaches ScheduleUnreadable:
  future schedule lines include the March fee even though January's corrected allocation does
  not. Report job retry is a consequence of that named refusal, not passing report evidence.

Next engineering work must align schedule placement with dated allocation using actual component
revenue evidence; realized allocation cannot universally replace recognized component revenue.
A royalty realized before satisfaction and a held fee are important counterexamples. Do not relax
`cuts.scheduled_after`'s sum check or proportionally scale future schedule lines to force a tie.
The revenue-waterfall reader also calls this shared schedule function and currently takes original
line amounts, so any adjusted placement must be consumed consistently there and in RPO, with
explanation lineage retained.

Additional pending review of the working-tree prototype: keep trace trimming sufficient for all
required dates; distinguish an absent legacy realization series from a traced zero amount; refuse
incomplete new trace evidence; avoid reading unrelated historical versions merely to collect
transition cuts; verify entry, cancellation and multiple-cause attribution, including a zero net
realized state after correction. Historical traces stay immutable and require release/replay
handling. This investigation does not close B4-2 or establish production readiness.


## Dated allocation and fixed schedule repair — October 8, 2026

The first-computation counterexample is repaired by the implementation following fa1db7f.
Recognition persists period/state realized allocation independently of recognized revenue. A
version with no fee component carries an explicit zero/NONE state; it is distinguishable from
an older trace that never recorded realization. Dated series require both state and period
evidence, including zero values. Missing evidence is not inferred from an absent node.

The report reader removes later realization when reading an earlier cut. RPO activity separates
fixed version-allocation changes from realized-fee movements. Entry/exit adjustments use dated
component evidence; a chain mixing legacy missing evidence and explicit realization is refused.
This requires legacy replay/upgrade handling before release, not historical trace mutation.

The engine also records fixed portions bound to their original schedule cause nodes. Report
placement removes future usage/royalty components using that decomposition rather than scaling
lines. Both RPO and the revenue waterfall consume the resulting amounts; the existing scheduled
sum check remains mandatory. A projection absent because manual adjustment, hold or Step-1
netting lacks supported component attribution is refused if needed for a scheduled figure.
This remains an implementation limitation, not permission to fabricate that split.

Cell contributors for projected amounts now name `scheduled_fixed_amount`. Its explain route
reads the unique component node from the same version's trace, with the original schedule line
and component inputs retained. Dedicated formula/narrative identifiers describe realization,
usage components and fixed schedule portions. Numeric primitives reuse the existing registered
sum/difference and posted-allocation arithmetic. These trace changes join the pending engine
0.4.0 release cut and candidate replay requirements; ENGINE_VERSION is not advanced prematurely.

The PostgreSQL witness checks January new contracts exactly 80,000, closing against January
posted subledger revenue, March variable-consideration additions 150, no unexplained amount and
both RPO tie-outs. It also generates January's journal through the normal API, checks the
waterfall recognized/scheduled/awaiting totals and its journal tie-out, and follows every RPO
cell contributor to a matching explanation. An intermediate expanded run had 47 passes and one
failure because the new waterfall assertion lacked a generated journal (expected journal revenue
zero versus actual 6,794.52); the test now supplies that required real journal, without weakening
the comparison. The corrected single witness passed in 11.51 seconds before final compatibility
changes; the final API/usage/explanation/access-scope suite passed 19 tests in 89.48 seconds.

Logs: `/private/tmp/rpo-fixed-schedule-expanded-db.log` (47 passes plus fixture failure),
`/private/tmp/rpo-waterfall-tie-baseline.log` (diagnostic),
`/private/tmp/rpo-waterfall-explain-fixed.log` (corrected witness), and
`/private/tmp/rpo-fixed-final-db.log` (final API suite). Earlier intermediate scoped checks:
262 engine/trace tests in 99.22 seconds; 111 units/trace checks in 1.74 seconds. These precede
explicit no-fee states and are superseded for changed behavior by the final combined check:
**614 recognition, disclosure, kernel, reader, version-chain, schedule and explanation tests
passed in 104.76 seconds**, `/private/tmp/rpo-fixed-final-engine-unit.log`. All 10 changed
source files pass mypy; changed Python files pass Ruff lint/format and git whitespace checks.

B4-2 remains partial: complete multi-cause fixed-allocation decomposition, projection attribution
under adjustments/holds/Step-1 netting, zero-net omitted schedule lines, mixed legacy upgrade
handling, royalty/entry/cancellation/calendar/exemption combinations and release cut/replays
still need coverage. No full backend/CI or production readiness is claimed. No deployment.
