# B4 change requests for `docs/04-DATA_MODEL.md` (from slug `numeric-residue`)

| Field | Value |
|---|---|
| Requester | Revenue accounting partner and engine engineer, post-B3 residue sweep (slug `numeric-residue`) |
| Date | 2026-09-12 |
| Applies to | `docs/04-DATA_MODEL.md` rev 1.2. The 04 owner applies these requests and adds its own revision row |
| Authority | `docs/01-DECISIONS.md` D-73 (04 owns column notes and payload members); D-77 (the sweep opens no question); `docs/accounting/answer-keys/_coverage/ADJUDICATION.md` section 10; `docs/reviews/B4-numeric-residue.md` |
| Effect on the build | Notes only. No column, type, default, constraint or enumeration changes. The answer keys already follow the new text |

## Requests

| # | Section | Old text | New text | Reason |
|---|---|---|---|---|
| R04-01 | §5 T-CON-08 `contract_version`, row `expected_returns_amount` | `` \| `expected_returns_amount` \| erev.money \| N \| `0` \| \| `` | `` \| `expected_returns_amount` \| erev.money \| N \| `0` \| ≤ 0. The build-up member `expected_returns` of ENGINE_SPEC S04-R-02, −Σ round(r × (Y + E)) (S04-R-08). Answer keys assert the signed figure, for example `"-300.00"` (rev 1.3; post-B3 residue sweep R-SGN-01). \| `` | ENGINE_SPEC S04-R-02 has always stated ≤ 0, but 04 carried no note, and four answer keys asserted magnitudes (BUILD_SPEC Appendix B.2 B3-BS2-13). The signed member is the only reading under which DB-17 V1 yields the gross allocation basis |
| R04-02 | §5 T-CON-08 `contract_version`, row `consideration_payable_amount` | `` \| `consideration_payable_amount` \| erev.money \| N \| `0` \| \| `` | `` \| `consideration_payable_amount` \| erev.money \| N \| `0` \| ≤ 0. The build-up member `consideration_payable` of ENGINE_SPEC S04-R-02, −Σ R of the promises dated on or before the version date (S04-R-14). DB-17 V1 subtracts it, which restores the allocation basis that excludes consideration payable released by JET-14 (rev 1.3; R-SGN-01). \| `` | As R04-01. `CPC-CHK-133-S3-EX32`: −1,500,000.00, with transaction price 13,500,000.00 and Σ `allocated_amount` 15,000,000.00 |
| R04-03 | §5 T-CON-08 `contract_version`, row `revenue_cum` | `` \| `revenue_cum` \| erev.money \| N \| \| \| `` | `` \| `revenue_cum` \| erev.money \| N \| \| Σ obligation `revenue_cum` less the cumulative JET-14 release, including share-based reductions (ENGINE_SPEC S04-R-02 rev 1.3). Obligation `revenue_cum` is gross of consideration payable. \| `` | The CPC keys assert a contract figure net of the release (`CPC-CHK-133-S3-EX32` 1,800,000.00) and an obligation figure gross of it (2,000,000.00), as DB-17 requires `allocated_amount = revenue_cum + scheduled_amount + awaiting_trigger_amount` with the gross allocation |
| R04-04 | §9 T-SRC-05 `source_invoice_line`, row `tax_lines` | `` \| `tax_lines` \| jsonb \| N \| `'[]'` \| Array of `{tax_type, jurisdiction, amount}`. \| `` | `` \| `tax_lines` \| jsonb \| N \| `'[]'` \| Array of `{tax_type, jurisdiction?, amount, principal_or_agent}`. The `BILLING_RECORDED` payload carries `{tax_type, amount, principal_or_agent}` (§16.3); `jurisdiction` is stored evidence and is not an event member (rev 1.3; post-B3 residue sweep R-SCH-16). \| `` | 04 held two member sets for one concept: T-SRC-05 `{tax_type, jurisdiction, amount}` and §16.3 `{tax_type, amount, principal_or_agent}` (rev 1.2, OQ-AK-13). The event payload governs the engine and the answer keys (dev-guide §9.5.5 rev 1.3). The source row needs `principal_or_agent` to feed the payload |

## Not requested

- No `CHECK (expected_returns_amount <= 0)` or `CHECK (consideration_payable_amount <= 0)`. A constraint would change migrations that the build loop may already have written; the engine invariant (ENGINE_SPEC S04-R-02) and the answer keys enforce the sign.
- No change to DB-17 V1. It already reads `transaction_price − consideration_payable_amount`, which is correct with the signed member.
