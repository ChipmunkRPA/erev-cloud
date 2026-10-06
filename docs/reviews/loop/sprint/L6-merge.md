# Sprint L6 merge: gates, integration fixes and answer-key failure clusters

Supervisor record of the Level 6 merge on main (2026-09-15 to 2026-09-16). The merge agent died on a model switch and its continuation stalled, so the supervisor ran the gates with `.run/l6merge/gates.sh` and fixed the integration defects on main.

## Integration fixes on main

- 4568053: the journal-run approval helper no longer redefines the exception-waiver `_literal` (mypy no-redef after L6-1 and L6-3).
- 2d8d40d: the GPA-5 amended-terms progress test expects the CPY-06 stored messages that DIN-7 builds.
- f6751fe: the SF-06 e2e approves with `subject_content_sha256`; `fetchExplanation` registers its node currencies before the panel renders (registration race on SF-03 `?explain=`).
- b61439c: `GET /journal-runs` sorts by `period` (SCREENS_B §3.1 binds SF-06 to `sort=-period`).
- 6fa3b50: SF-06:run-lines hosts an ExplainProvider and docks the panel.

## Answer-key failure clusters and parity

- L6 release-gate answer keys on main at 2d8d40d: 135 of 175 (D-87 selection). No merge regression against lane L6-5; the merge fixed DISC-S10-DISCLOSURES-RPO-EX42. Failure clusters (40 keys):
  - Ruled in D-87, lane L7-5 (engine fix lane D):
    - L6-5-Q-10 stage 06 CONCESSION component: RND-CHK-003C, VC-CHK-113-TC-POBVC-16
    - L6-5-Q-12 runner activation and S04-R-09 constrained form: STP1-S1-EX1-CASEA, STP1-S1-EX1-CASEB-C-VARC, STP1-S1-EX2 (FX-CHK-084-B also needs Q-26)
    - L6-5-Q-25 return-right expiry at the window end: RET-CHK-116, RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET (also L5-3-Q-5)
    - L6-5-Q-27 catch-up alias: VC-CHK-101-S3-EX23-CASEB (JE-CHK-025 also needs L5-3-Q-7)
    - L5-3-Q-8 financing without a payment schedule: SFC-S3-EX29, SFC-CHK-136-S3-EX29-ANNUAL, SFC-FS-11-CASEB-UPFRONT-ADVANCE-ACCRETION, JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION
    - L5-3-Q-19 terms-form modification lines: MOD-FS-09-CANCELLATION-REFUND-COMMISSION, MOD-FS-10-CLOUD-CONVERSION-CREDIT, MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION
  - Ruled in D-87, lane L7-6 (engine fix lane E):
    - L5-3-Q-7 = L6-5-Q-11 refund liability without a target: VC-S3-EX24, JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY, RET-WM-04-REFUNDS-AND-CHARGEBACKS, VC-BR-02-DISTRIBUTOR-RETRO-REBATE, VC-RB-04-COST-REPORT-SETTLEMENT, RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION (also L5-3-Q-9, lane D)
    - L6-5-Q-14 ERP layer date: FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15
    - L6-5-Q-15, Q-25, Q-26 credits, expiry and release amounts: FX-CHK-084-A-REFUND-LIABILITY-REMEASURED; L6-5-Q-12, Q-26: FX-CHK-084-B-DEPOSIT-LIABILITY-REMEASURED
    - L6-5-Q-18 T-CON-09 functional columns: FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED
    - L4-3-Q-24 agent gross relief: POB-S2-EX45-AGENT-AGENT, POB-WM-01-THIRD-PARTY-COMMISSIONS-NET, POB-WM-05-HOTEL-MERCHANT-VERSUS-AGENCY
  - Unruled, diagnosed by the lanes in their last batch:
    - Lane D: ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT (transaction price keeps the routed-out lease: 108,000.00 against 27,000.00); ALC-CHK-032-S4-EX34-CASEC-REJECTED (RESIDUAL_REJECTED); ALC-S4-EX35-CASEB (royalty price 300.00 against 500.00); ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION (S04-R-02 invariant); ONB-RB-06-RELIEF-GRANT-ROUTED-OUT (TOTAL_SSP_ZERO); REC-S5-UPFRONTFEE-OWN-A and -B (upfront fee allocation and JET lines); MOD-CHK-112 (S06-R-21 MOD-TERM line; L5-3-Q-20, L5-5-Q-21)
    - Lane E: COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT and COST-S8-CONTRACT-COSTS-IMPAIRMENT (amortization, impairment and revenue_cum figures); DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT (pre-standard lines posted with reversed signs); JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE (billed_cum 1,000.00 against 0.00 for a cancellable invoice)
- L6 parity on main: 93 of 121 (`not point_in_time_equivalence`); every GPA-2 to GPA-5 case passes (93 of 93). The 28 failures are journal_entry_totals (24: steps 02 to 14, months 2023-01 to 2023-10 and the full year; GPB-1, GPB-2) and legacy_probe P1 to P4 (GPA-6), all lane L7-1.
