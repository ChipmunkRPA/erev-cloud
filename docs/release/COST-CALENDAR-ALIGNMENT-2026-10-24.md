# Contract costs across aligned calendars — October 24, 2026

## Feature

Contract cost rollforward previously refused different calendar records even if their complete
selected periods and opening boundary were identical. Its existing reader already resolves each
entity's own periods, original costs and currency rates. The report admission now uses the same
complete-range proof as the balance and RPO rollforwards.

The request must provide both from_period_key and to_period_key. Every calendar must contain
those keys, the same contiguous intervening period definitions and the same preceding period.
Matching only the first and last date is insufficient. Different dates, missing endpoints,
different interior periods or inconsistent opening history still refuse with CALENDARS_DIFFER.
There is no allocation of partial fiscal periods or relabelling of incompatible fiscal keys.

## Necessary verification

A public workflow creates an independent January calendar and a second active contract with a
24,000 commission beside the existing contract's 12,000 commission. August–September costs
run jointly in transaction, functional and reporting views. Each entity/category/movement
matches its independent run, closing assets are positive, the carrying checks pass, and saved
reruns retain identical output hashes. This fixture uses USD for all three views; differing
reporting FX arithmetic is covered by the existing retained-monthly-rates test, not claimed
as additional new coverage here.

A separate April calendar with the same requested fiscal keys is refused through the public
API. The existing calendar-admission workflow and focused interval proof cover refusal of
incompatible selection, missing boundaries and changed interior/opening definitions. Scoped
lint and types pass.

No schema migration, journal change or deployment. Broader unmatched-calendar reports and
other documented development gaps remain separate work.
