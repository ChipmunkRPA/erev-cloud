# Agent POB source ownership within combinations — October 23, 2026

This extends [contract FIFO source support](AGENT-CONTRACT-FIFO-2026-10-23.md)
to FIFO_WITHIN_POB across transaction, functional and reporting views.

New POB reports admit original agent revenue sources owned by another member of the same
selected computation group. Membership comes from the retained report versions, not the
current combination table. Sources outside that group remain refused.

This does not move the receiving member's opening balance to the recognizing member.
Original attributed POB billing less gross control relief still sets each POB's opening
cap. Verified net source income adds a further cap; the group cap is applied once. Combined
disclosures retain one group amount and the complete member/source set without allocating
that final amount to members.

The existing zero-consumption rule now reaches POB agent source reading. Reporting permits
the shortcut only when every period has no positive consumption; otherwise original source
classification is still required.

New source-set revision 3 selects this behavior. Revision-1 and revision-2 saved reports keep
their original source scope and zero-consumption behavior. The report footnote recognizes
all supported saved versions.

## Related zero-balance FX restoration

The combined historical-prepayment/refund scenario also exposed a rollforward failure:
a retained negative FX adjustment restored an original opening source after its carrying
balance reached zero, but replay had discarded that source bucket. Replay now retains the
zero opening bucket. Original-source negative FX may restore it; positive FX still cannot
overdraw it, and unknown named layers remain rejected. Posting amounts and source identities
are unchanged. The full member bridge must still reconcile; no OTHER amount is used to
derive the restoration.

## Verification

88 focused cases cover selected-group ownership, rejection of outside owners, preservation of
the original POB opening cap, old source-version selection, signed currency translation and
zero-consumption safeguards. Two populated combined-contract scenarios pass, exercising both original
prepayments and current-period receipts, three currency views, contract and POB FIFO,
report explanation and saved reruns. Existing refund and return checks remain in place, including the zero-balance FX restoration.
Scoped types, lint and whitespace checks pass.

## Remaining boundaries

Positive-consumption mixed opening/non-opening agent source sets still lack unique net amounts
by source. Cross-entity/acquired source support and sources outside the selected historical
group remain unfinished. No source amount is inferred from gross proportions.

No engine posting change or deployment.
