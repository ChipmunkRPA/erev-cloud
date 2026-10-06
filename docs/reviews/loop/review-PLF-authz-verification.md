# PLF review addendum: authorization verification and cross-tenant IDOR sweep

| Field | Value |
|---|---|
| Date | 2026-09-13 |
| Commit reviewed | 0eb193d (review worktree `~/dev/erev-rv/plf`, databases `erev_rv_*`) |
| Why | The PLF review's authz-tenancy lens returned no findings list, so PR-Z-01 and PR-Z-02 rested on the lead's probe alone. There had also been no route-level IDOR sweep |
| Evidence | `~/dev/erev-rv/reports/plf/verify-authz/` (repro and authority probes, `idor-sweep/test_idor_sweep.py`, `results.md`, logs) |

## Verdicts

| Finding | Reproduction verifier | Authority verifier | Result |
|---|---|---|---|
| PR-Z-01 cross-tenant MFA reset through an invitation (P1) | Confirmed | Confirmed; P1 justified | **Confirmed P1.** Any Tenant Admin who knows a user's email can invite it (201 INVITED) and then reset MFA (200). The victim's global factor is disabled and every session ends, including platform operators'. The audit lands only in the acting tenant. With the victim's password this is an account takeover |
| PR-Z-02 global identity data through an unaccepted invitation (P2) | Confirmed | Confirmed; P2 holds, narrowed | **Confirmed P2.** The response discloses global `display_name`, `last_login_at` and `mfa_enrolled`, and acts as an existence oracle for platform-wide users. The rename is limited to identities with no password and no IdP. The sub-claim that the audit should reach the user's other tenants is not a T-PLT-02 violation when the user has no ACTIVE membership |

Corrections from the verifiers:
- For an ended operator session, `GET /session` returns 200 `AnonymousSessionOut`, not 401.
- No loop commit touched `users.py` or `auth/` between 0eb193d and 3406b41.

## IDOR sweep

46 route templates were exercised as tenant B's admin with tenant A's ids (inventory: 105 routes, 40 with a path id):
- All 34 path-id routes return 404 for A's real id and for a random id: no cross-tenant access and no existence oracle.
- The 4 creates carrying foreign ids in the body return 422 and write nothing.
- The 5 list filters taking foreign ids return 200 with 0 items.
- A bulk approval mixing both tenants' ids gives a per-item not-found.

Only the invitation vector leaks. It is keyed by the victim's email, not a crafted id, and gives PR-I-01 (= PR-Z-01, P1) and PR-I-02 (= PR-Z-02, P2).

## Disposition

No new items. PR-Z-01 and PR-I-01 are remediated by WEB-3a, and PR-Z-02 and PR-I-02 by WEB-3b, under D-80:
- status ACTIVE or SUSPENDED required for reset;
- operator targets return 404 and operator emails refused at invitation;
- reset audit fanned out to each ACTIVE membership;
- identity fields redacted until acceptance;
- rename only for identities the invitation created.
