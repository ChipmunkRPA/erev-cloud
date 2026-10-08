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
