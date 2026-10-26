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
- Acquisition reporting for supported calculations, including original monthly mixed-group
  snapshots, signed group changes and separate member endpoint presentation.

## Completion status

The remaining foreign split, return-asset and loss-provision implementation is complete for
its documented scope. Focused calculation, journal and report-source checks accompany it.
Deployment and independent accounting review remain outside repository development.

Broader performing-agent calendars and additional acquisition scenarios are outside the
completed implementation. Unsupported calculations and incomplete historical source evidence
remain explicit refusals.

See [current scope](docs/release/CURRENT-DEVELOPMENT-SCOPE.md) and
[mixed acquisition reporting](docs/release/MIXED-ACQUISITION-REPORTING-2026-10-26.md).
