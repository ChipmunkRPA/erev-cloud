# eRev Cloud: supported scope and limits

This is the public summary of the repository's current calculation and reporting boundaries.
See [current scope](CURRENT-DEVELOPMENT-SCOPE.md) and [project status](../../PROGRESS.md).
Use is subject to Apache License 2.0.

## Completed reporting and currency work

Reports include contract balances and rollforwards, revenue and RPO disclosures, practical
exemptions, contract costs, modification and variance attribution, and GL reconciliation.
Supported transaction, functional and reporting views retain their original sources and rates.
Saved runs reproduce from retained inputs; unavailable historical evidence refuses explicitly.

Foreign fixed-service splits preserve earlier revenue and distribute remaining original FX
layers across effective destinations. Rates, source contracts and collection ages survive
successive splits. Newly exposed gross liabilities restore historical credit carrying;
monetary assets use split-date spot and the difference is recorded as FX. Group rollforwards
show reclassifications and FX separately. Member endpoints remain visible without invented
member movement allocations. Current liability follows destination release layers and member
carrying balances.

Foreign return assets retain original delivery unit-cost and FX layers. Recovery costs use
the assessment-date rate, and releases follow the existing FIFO/pro-rata policy. Functional
loss provisions use historical actual revenue and costs plus dated remaining forecasts;
the loss register reads the original test and retained reporting rates.

## Calculation boundaries

- Contract-group separation preserves existing variable consideration, estimates, returns,
  breakage, financing and noncash state alongside fixed service. It keeps original obligations
  and source ledgers; obligation transfers retain their separate eligibility rules. Historical
  return entitlements remain with original deliveries, with future-service allocation and
  release rates retained through successive separations.
- Performing-agent commission transfers require aligned period dates. Broader calendar
  combinations are outside the completed implementation.
- Acquisition work covers reporting for already supported calculations, including monthly
  mixed-group snapshots and separate member endpoints. Additional acquisition scenarios
  and unsupported acquisition/entity/agent combinations are outside this reporting work.
- Earlier evidence revisions retain their original interpretation. Missing source events,
  rates, membership, original computations or trace evidence require correction or recomputation;
  reports do not fabricate historical amounts or source allocations.

## Verification and repository scope

Focused checks cover trace replay, layer conservation, journal reconciliation, FIFO/pro-rata
releases, independent functional return/loss calculations and report projections. An isolated
PostgreSQL application workflow also verifies approved foreign split persistence, all three
currency views, original explanation links, exact retained reruns and functional aging.
These checks establish the exercised behavior rather than universal contract-scenario coverage.

Repository completion covers software and documentation. Deployment, promotion of migration
data into live business operations and independent accounting review are outside that work.
Material accounting actions retain the implemented approval and separation-of-duties controls.
Sandbox refresh creates an editable copy; reproducing production period locks is not required.
