# Reporting-currency disclosure packs and contract costs

Live disclosure packs now accept the tenant's reporting currency across all nine child reports,
including period and quarter-to-date selections. Parent/child currency checks and retained-input
reconstruction continue to enforce one selected basis. Migration 0345 updates the frozen report
catalogue metadata. The existing schema-driven report UI exposes the new choice.

Contract cost rollforward previously accepted reporting currency but returned original amounts.
New runs now translate original functional cost movements month by month: opening/closing carrying
amounts at their corresponding closing rates, signed movements at monthly averages. Currency
translation and Translation rounding appear as separate rows. Each month's endpoints are allocated
across cost kinds using largest remainder, preserving the translated entity total. Monthly movements
and FX accumulate across the selected range; the first opening and final closing remain endpoints.
Missing original posting dates, required rates, or functional carrying sources refuse the projection.

The original functional cost rollforward must still reconcile to computed contract carrying amounts.
Its result is retained in control totals and the public tie-out details. A failed source check cannot
be turned into a pass by translation. Approved rate identities are bound for reruns. Previously saved
reporting-view runs without the new projection evidence retain their prior rows and semantics.
Transaction and functional rows keep their existing format.

Necessary verification:
- Public foreign-contract disclosure pack: USD 54,000 revenue recognized as GBP 43,200 is presented
  as USD 53,333.33 using the approved reporting average. All nine children use the reporting view;
  the pack succeeds and its retained rerun has the same output digest.
- Public nonempty commission cost report: USD 8,005.48 opening / 493.15 amortization / 7,512.33 closing
  become GBP 5,603.84 / (394.52) / 6,761.10, with 1,551.78 translation and zero rounding. Original and
  translated carrying checks pass, and the saved rerun has an identical digest.
- Fourteen focused unit cases pass, including changing monthly rates, category endpoint rounding,
  missing opening periods, retained source failures, existing cost rows and all disclosure choices.
- Migrated catalogue parity, scoped lint and Python types pass.

No deployment. Existing locked packs/snapshots keep their original currency basis; this does not
add currency-specific lock snapshot production or foreign cost accounting in the posting engine.
