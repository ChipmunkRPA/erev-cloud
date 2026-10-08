# Independent accounting review — pending

Prepared October 7, 2026; accounting corpus evidence updated October 8. This is a review request and evidence index, not a certification.
Repository work is authorized; deployment is excluded. No independent reviewer or sign-off has
been recorded. Passing software tests does not establish compliance with ASC606 or ASC830.

## Decision required: contract-liability FX classification changes

POL-163 allows an ASC606 contract exception for refundable advance consideration. Current
calculation inputs select an approved value by contract, contracting entity and period; approval
is the effective instant for that selection. IFRS15 retains its framework-forced treatment.
The public authoring endpoint remains disabled for this policy.

A change in contractual refund rights and a correction of an erroneous classification may need
different accounting. The current override record provides neither a separate economic effective
date nor an explicit distinction between those cases. The reviewer should resolve those points
before a transition calculation is implemented or the public feature is enabled.

### Reproduced case

| Event | Transaction amount | Functional amount (USD) |
| --- | ---: | ---: |
| January advance, spot 1.10 | EUR 12,000 | 13,200 |
| January monetary close, rate 1.12 | EUR 12,000 outstanding | 13,440 |
| Cumulative FX loss after January | — | 240 |
| February full relief using original historical basis | EUR 12,000 | 13,200 |
| Residue left by that combination of treatments | EUR 0 | 240 |

The earlier engine silently omitted the empty layer with that functional residue. The current
check refuses the calculation, preserving the previous persisted head and ledger. Cases with a
negative residue, a partial release, and no release are also covered. Refusal prevents an
unreconciled output; it does not complete transition support.

The reviewer should specify:

1. What facts make each advance monetary, including partial refundability, and whether a
   contract-level classification is sufficient for contracts with several different advances.
2. How to distinguish a correction from a prospective change in refund rights; which economic
   date and evidence must be stored, and whether period-based selection is adequate.
3. The required basis at transition, exchange rate, treatment of previously recognized FX and
   subsequent revenue relief, including partially consumed layers and transaction rounding.
4. Treatment of changes recorded after a period is locked, with restatement or current-period
   adjustment requirements, and required independent approval.
5. The expected entries and closing balances for both directions of transition, combined groups,
   partial releases and refunds, and the permitted differences between ASC606 and IFRS15.

Do not resolve a residue by silently dropping it, editing the original layer amount, or creating
an unexplained balancing entry. Implement the reviewed treatment with dated facts and traceable
entries, then validate it against reviewer-supplied examples.

## Current evidence

- `backend/tests/engine/s12_fx_entities/test_s12_remeasurement.py`: member isolation, encoded
  identifiers, IFRS treatment, historical periods, and positive/negative transition residues.
- `backend/tests/domain/contracts/test_fx_remeasurement_recompute.py`: actual approval,
  persisted close-pass journals, repeat-run idempotency and preservation of the saved calculation
  when a transition is refused.
- `backend/tests/domain/close/test_close_run_inputs.py`: a real close job becomes out of date
  after an effective contract exception; same-value, unapproved and later-period changes do not
  change the policy digest. The following run records the effective value.
- `backend/tests/domain/close/test_policy_approval_lock_race.py`: real approved waivers,
  policy approvals and period-lock decisions in both orders; an approval overtaken by a lock
  rolls back and remains available for a later decision.
- `PROGRESS.md`: dated test results and publication record.
- `LIMITS-1.0.md`: broader outstanding system limitations. This packet covers the FX and concession decisions;
  final sign-off must review the full implemented ASC606 scope and remaining limitations.

## Decision required: concession after modification (AD-14 and AD-15)

The October 8 full database accounting-corpus gate reproduced all seven differences for
`VC-CHK-113-TC-POBVC-16`. The key expects software billed to date of 400.00; the engine
states 364.98. After a 60.00 concession, the key expects a refund liability; the engine states
a contract liability. Corresponding November refund-liability and December release entries
differ. See [the dated gate evidence](REPOSITORY-CHECKS-2026-10-08.md) for the immutable
revision, run scope and report hashes. The key remains pending review and failing.

Review the key's modification, billing allocation, targeted concession and credit-memo facts.
Resolve AD-14 and AD-15 with expected obligation billing, balances and journal entries at all
three checkpoints. Establish whether the fixture/expectations, calculation, or both need repair;
no expected value has been changed merely to agree with the current implementation.

The separate legacy journal key cannot complete its nondistinct review because the fixture lacks
an integration target. Completing that scenario requires explicit supported facts, preserving
its intended independent journal comparisons. All 255 corpus key review statuses are still
unapproved, and the parity gate separately lists five pending deviation approval units. A passing
subset or complete coverage inventory does not substitute for these reviews.

## Sign-off record

| Required evidence | Status |
| --- | --- |
| Independent reviewer identity and qualifications | Pending |
| Scope, accounting basis and dated decisions | Pending |
| Reviewed numerical examples and expected entries | Pending |
| Implementation and immutable revision reviewed | Pending |
| Exceptions accepted and limitations disclosed | Pending |
| Reviewer approval with date and evidence reference | Pending |

No field is to be marked approved without actual evidence from the independent reviewer.
