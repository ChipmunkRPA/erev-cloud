# Royalty correction after eligibility exit — implemented October 22, 2026

The owner selected downward correction of previously recognized income while NOT_A_CONTRACT,
with no new recognition until re-entry. The original reproducer was a delivered functional
licence with a 1,200 guarantee, January royalties of 600 and February royalties of 1,000 before
collectibility exit. A March correction to February of 800 previously left recognized revenue
at 1,600 against allocation of 1,400 and failed S09-INV-03.

Stage 09 now evaluates corrections to the original recognized usage periods in event order,
retaining the lowest royalty target reached during exclusion. The reproducer recognizes a
March reversal of 200 and ends at 1,400. New usage periods, later satisfaction and upward
revisions cannot generate excluded-period income. A later upward correction after the reversal
also leaves income at 1,400 until re-entry. The fixed guarantee and licence progress remain
frozen; normal recognition resumes under the existing re-entry logic.

The reduced target retains the actual statement/estimate input set and can be recomputed from
its trace. This path applies to corrections of original usage-period windows; it does not invent
allocations for statements that rebucket sales into different windows.

Necessary verification: 39 ordered-eligibility/RPO cases pass, including nine exit cases covering
downward correction, upward correction, upward rebound, statement before/after same-day exit,
and satisfaction before/after exit. The new cases re-evaluate the complete native trace and
check zero unexplained RPO movement. Existing same-day re-entry cases remain covered.
This is bounded development evidence, not an independent accounting opinion.
