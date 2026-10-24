# Shared breakage: foreign SSP allocation preview

The saved shared-breakage version's allocation preview now supports members whose transaction
currency differs from the shared estimate currency. Previously the endpoint refused that population.

Each foreign SSP weight uses a published direct spot rate on or before the estimate effective date.
The preview retains the original SSP, currency pair, effective date, rate date, rate key and publication
version. The viewer exposes those sources alongside the converted weight. Same-currency rows retain
their existing weights and require no FX publication. No inversion or triangulation is inferred.

Weights retain exact decimal multiplication precision, including values below a currency minor unit.
Existing largest-remainder quantity allocation conserves the entered total at 18 decimal places;
entitlement caps still refuse excess instead of redistributing it. Missing direct rates refuse the
whole preview. Dirty or incomplete computed populations retain their existing refusals.

This is a current-computation preview, not an approved or frozen application basis. Refresh can
select a newer FX publication. Breakage submission/application and effective-date SSP freezing remain
unfinished; the expected-redemption denominator decision is still pending. No journals change.

Validation: 15 focused backend cases cover allocation, currency-weight changes, original sources,
missing/inverse/future rates and tiny exact weights. The focused viewer scenario verifies source
presentation and removal of obsolete results after a refused refresh. Scoped lint, Python types and
frontend TypeScript checks pass. No deployment.


## October 24 original-identity correction

Preview allocation now uses the engine's encoded contract/obligation subject key instead of
joining raw identifiers with a slash. Previously (contract A/B, obligation C) and (contract A,
obligation B/C) collided and incorrectly refused a complete population. Literal percent escapes
must also remain distinct from slash characters. Original API identity fields are unchanged.

The regression checks retain both original version identities and the distinct 100/200 SSP
weights, producing 3/6 of a total breakage quantity of 9. Seventeen focused allocation/preview
cases pass, with scoped lint/types. This is a preview correctness fix; frozen effective-date
application and the pending expected-redemption rule remain unfinished. No deployment.


## Selected breakage targets — October 24, 2026

Shared BREAKAGE definitions now accept common target obligation keys in the settings UI and
save their resolved original obligation IDs through the existing definition command. Every
current member must contain every selected key. Allocation preview limits eligible current
computed obligations to those keys and refuses a member with a missing, out-of-scope or
non-redemption/non-loyalty target. Leaving targets blank retains the existing all-eligible
population. This lets a portfolio allocate its total breakage only to a selected points program
without including unrelated eligible programs on the same contracts.

Necessary verification: 20 focused preview/allocation cases, including two members with
unrelated eligible obligations, missing member targets and original-ID target resolution;
12 portfolio UI cases, including both shared kinds submitting selected keys. Scoped Python
lint/types and frontend TypeScript/ESLint pass. These are service and UI checks, not a new
PostgreSQL approval/application journey. No migration or deployment.

The preview still uses current computed SSP. Frozen effective-date allocation and shared
breakage approval/application remain unfinished; this does not change recognition inputs.
