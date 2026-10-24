# Functional-currency disclosure packs

Live disclosure packs now accept transaction (the existing default) or functional currency.
The selected view is passed to all nine child report types, for period and quarter-to-date
selectors. Child attachment checks, source capture and retained-input reconstruction verify
that every child uses its parent's currency basis. The existing report parameter UI receives
the choice from the catalogue. Migration 0344 updates the stored catalogue with frozen old/new
metadata; the user guide describes the selection.

Existing lock snapshots retain transaction sources. An explicit transaction selection is accepted;
a functional selection is refused rather than relabelling frozen values. This does not add
reporting-currency packs or functional lock snapshot production. Cost movements retain their
existing original functional-currency requirements; unposted FX differences still fail the
opening-relief reconciliation instead of being waived by the pack.

A populated foreign-contract exercise exposed an unnecessary RPO requirement: a new contract with
zero opening RPO required the preceding period's FX rate. New runs omit that zero-valued opening
rate term. Nonzero openings retain the rate requirement. Saved runs without the new evidence flag
retain their original source population; new saved runs retain the selected rule. Current period
average and closing rates remain required.

Validation:
- Public USD contract/GBP entity: a USD 90,000 prepayment and USD 54,000 delivered revenue produce
  GBP 43,200 disclosed revenue. All nine child outputs use GBP, the parent succeeds and its
  saved rerun has the same output digest.
- Existing period/QTD transaction workflow passes child retry, assembly, XLSX, publication,
  saved replay and frozen-lock checks.
- 59 focused unit cases pass across child planning/assembly, lock selectors, catalogue metadata
  and RPO translation, including legacy versus new zero-opening source populations.
- Full migrated report-definition/catalogue parity passes. This also exposed and repaired missing
  code catalogue POB source descriptions already installed by migration 0342; no historical report
  output or posting changes were made for that metadata repair. Scoped lint and Python types pass.

No deployment. Broader Reporting and repository gaps remain open.
