# Contract-review document fixture

`Kinsley-Marrow-Order-Form-2026-10.pdf` is a synthetic four-page order form generated
for PRD WLD-F-29 / J-19.2. It is not a real customer agreement or accounting evidence.
Its fields and expected confidences come from that documented example. No currency,
collectibility decision, approval or revenue schedule is inferred by this fixture.

The document was generated with ReportLab using built-in Helvetica, invariant PDF
metadata and compressed page streams. All four rendered pages were visually checked.
ReportLab is an authoring tool, not a runtime dependency. The committed PDF is the
source artifact consumed by tests through the pinned pypdf extraction adapter.

The exact-input response is retained under `../contract-review/v1/`. The request uses
document UUID `00000000-0000-0000-0000-000000000029`, model `fixture-model`, 16,000
maximum tokens, contact redaction enabled, and the nine field paths in
`test_pdf_extraction.py`. Token usage in the response is synthetic. The test loads
this retained response through FakeProvider; it does not invoke a model or write a
proposal. There is no default-response fallback for unrelated documents.

These paths are extraction proposal paths. Applying them through the production
contract command schema, approval workflow and human acceptance remains separate work.
