# Return credit memo original-invoice entry

The return drawer now accepts an optional original invoice number and retains it in the
CREDIT_MEMO_RECORDED payload, including forecast-draft and preview paths through the shared
builder. Whitespace is trimmed; blank references are omitted. Entering a reference without a
credit memo number produces a field error instead of silently discarding the source. The existing
selected-obligation target, approval route and positive credit amount requirements remain.

Necessary verification: all 16 event-drawer cases pass, including the blocked dangling reference
and submitted return/credit batch. Frontend types/lint pass. Four connected native billing/FX/
public-opening-reader cases pass for full and partial credits, with shared and directly attributed
original invoices. Original invoices of EUR 3.00 at USD 3.01, credited by EUR 1.00 at USD 1.00,
retain USD 2.01; when the original invoice belongs solely to P1, the unreferenced linked credit
also belongs to P1, despite equal contract allocation across three obligations. Trace replay and
unchanged FX movements/targets with evidence removed are checked.

The previous native witness used `invoice_number` on the credit payload. The engine reads
`credited_invoice_number`, so that witness exercised fallback allocation rather than the claimed
original-invoice association. This checkpoint corrects the witness and proves both allocation
shapes. It does not claim completion of mixed-position credit populations, agent/acquired/cross-
entity opening sources, or combined reassessment. No backend behavior/schema change or deployment.
