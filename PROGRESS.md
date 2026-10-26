# Project status

This repository provides eRev Cloud revenue-recognition software for ASC606 and IFRS15,
under its noncommercial license. Repository completion does not include deployment.

## Available functionality

- Contract and obligation management, allocation, recognition schedules, supported contract
  modifications and variable consideration.
- Journals, source explanations, contract balances and rollforwards, revenue/RPO disclosures,
  contract costs, variance attribution and GL reconciliation.
- Supported transaction, functional and reporting-currency views, retained source evidence,
  disclosure snapshots and saved-input report reruns.
- Explicit combined-member royalty scope and corrections, shared estimates/breakage,
  supported prospective splits and aligned-calendar performing-agent commissions.
- Historical foreign cost capitalization and clawbacks, independently measured functional
  impairment and book-specific capped reversal behavior.
- Foreign return assets retaining delivery cost/rate layers, dated recovery costs and the
  existing release policy. Loss provisions use historical actuals plus dated remaining
  forecasts; the loss register reads original functional tests and reporting rates.
- Foreign split continuation with conserved destination layers, original rate/source/age,
  explicit gross reclassification and source-bound monthly rollforwards.
- Contract-group separation continuing existing variable consideration, estimates,
  returns/refunds, breakage, financing and noncash state. Historical revenue and return
  entitlements remain with their sources; only remaining service is redistributed.
- Acquisition reporting for supported calculations, including original monthly mixed-group
  snapshots, signed group changes and separate member endpoint presentation.

## Completion status

Contract-group separation now supports the existing specialist accounting treatments as well
as the completed foreign-layer, return-asset and loss-provision work. Focused checks cover
native recognition, remaining SSP, return release order, successive separations, RPO,
balance/journal reconciliation and source-backed reports.
The approved foreign separation workflow, including noncash consideration, is also verified through persisted PostgreSQL data,
all three currency views, original trace links, exact retained reruns and functional aging.
Deployment and independent accounting review remain outside repository development.

Broader performing-agent calendars and additional acquisition scenarios are outside the
completed implementation. Unsupported calculations and incomplete historical source evidence
remain explicit refusals.

See [current scope](docs/release/CURRENT-DEVELOPMENT-SCOPE.md) and
[mixed acquisition reporting](docs/release/MIXED-ACQUISITION-REPORTING-2026-10-26.md).
