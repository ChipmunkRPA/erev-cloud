# Dimensionless shared return rates across currencies — October 23, 2026

Shared return versions with only a rate can now apply to members whose transaction currency
differs from the version's denomination. A rate carries no money to convert. Missing monetary
inputs and explicit zero amounts are accepted; nonzero carrying/recovery cost, other monetary
amounts or monetary scenarios retain the existing currency-match requirement. Non-finite or
invalid monetary values refuse calculation. Total-quantity versions remain unsupported.

The source version currency and original rate are retained. No amount is relabelled and no FX
rate is fabricated. Impact preview continues to show each group's actual transaction currency;
approval uses those group effects for routing. The editor explains the restriction.

Necessary verification:

- 42 focused loader/native cases passed. Actual return recognition is identical for USD- and
  GBP-denominated shared rates with zero monetary inputs (January revenue 9,200.00), including
  effective-date precedence and retained local history.
- Public PostgreSQL API saves a GBP rate-only successor, previews a USD member, independently
  approves and applies it without any GBP/USD rate. Passed.
- Loader rejects nonzero, negative and non-finite foreign recovery costs. Scoped lint/types pass.

This does not implement cross-currency monetary cost conversion, shared breakage application,
agent opening-income attribution or combination reassessment. Those remain unfinished. No
posting formula or report translation rule changed; no deployment or full-readiness claim.
