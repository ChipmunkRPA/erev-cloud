# Original cost-asset rollforward detail — 2026-10-24

The cost rollforward now offers category or original-asset granularity in the report toolbar.
Asset rows retain the posted subject identity, original contract, cost category and all eight
rollforward lines. Missing or inconsistent asset identity refuses rather than inventing a
surrogate grouping. Transaction, functional and reporting views use the same retained sources.
Reporting endpoints allocate within category totals; signed movement and FX rounding also
preserves each category line. This keeps detail totals aligned with the category view.

Migration 0347 admits the optional grouping parameter in existing databases. Default category
runs and old saved runs retain their shape. Existing lock datasets only contain category totals;
asset grouping with a lock ID is refused explicitly pending a dedicated frozen asset dataset.

Validation: 17 focused report tests, 9 toolbar tests, and a real database workflow that creates
two cost assets and reconciles every detail line to category totals. Reporting rounding uses
three assets across two categories; posted source/legacy-binding cases remain covered. Scoped
Python and frontend checks pass. No deployment. Remaining native specialist currency limits
and the frozen asset dataset are not claimed complete.
