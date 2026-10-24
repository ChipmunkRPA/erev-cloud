# Original acquisition liability layer sources — October 24, 2026

Revision 46 retains the original open contract-liability layers at the acquisition
cutover for the supported singleton foreign-currency nonposting observation.
Each layer includes remaining transaction quantity, functional carrying amount,
and original creation, consumption and remeasurement movements with dated rate
versions and trace nodes. This adds evidence; it does not change postings.

The report reader validates movement node values and currencies, original rate
versions and values, reconciles each layer from movements, and reconciles the
sum of open functional carrying amounts to the original liability total.
Contract-balance cell explanations show the original layers and link to their
movement traces. Existing saved observations below revision 46 remain readable.

Necessary verification: focused public foreign acquisition report and saved
rerun passed (1 case); native acquisition and movement reconciliation checks
passed (10 cases), including changed source/rate/amount and signed remeasurement
checks. Scoped Ruff and mypy passed. The public example reconciles EUR 20,000
remaining liability to USD 22,000 at original rates. No deployment.

Still open: the owner's functional current/noncurrent classification policy,
full foreign functional/reporting balance views, and broader combined/agent
acquisition support. No future income amount is assigned to an individual layer.
