# Current development scope

This page describes the public repository's supported behavior and documented engineering
limits. It is not a certification of accounting compliance or a deployment approval.

## Repository scope

The project implements revenue recognition for ASC606 and IFRS15. It includes contract and
obligation management, transaction-price allocation, recognition schedules, supported contract
modifications, variable consideration, journals, reports and source explanations. Use is subject
to the repository's noncommercial license.

Development completion targets the repository. Live deployment, promotion of migration data
into actual business operations and independent accounting review are outside that scope.
Approval controls concentrate on material accounting actions and separation of duties.
Sandboxes can be refreshed from production data and permit unrestricted experimentation;
replicating production period locks is not a sandbox requirement.

## Reporting

Reports include contract balances and rollforwards, bookings/billings/revenue, revenue
waterfalls, RPO and exemptions, cost assets, contract modifications, variance attribution,
disclosure packs and GL reconciliation. Supported reports retain original sources for cell
explanations and saved-input reruns.

Transaction, functional and reporting-currency views use retained rates and source evidence.
Reporting translation, remeasurement and rounding have separate classifications. Contract
liability current/noncurrent presentation follows the original release layers; member current
liabilities are apportioned by member carrying balances. Original collection age remains with
its collection contract, with member allocation adjustments presented separately.

Acquisition work is limited to reporting for calculations already supported. Mixed acquired
and existing principal groups use original monthly group snapshots and signed acquisition
changes. Member opening/closing balances remain visible, while unsupported member movement
allocations remain unavailable. Group movements contribute once to totals. Complete member
sources, original hashes and trace links support explanations and retained reruns. Missing or
inconsistent original evidence refuses explicitly. No additional acquisition scenarios are
included in this reporting wrap-up.

See [mixed acquisition reporting](MIXED-ACQUISITION-REPORTING-2026-10-26.md) for its focused
validation and presentation details.

## Recent calculation coverage

- Combined-member royalties require explicit combination-wide or member-only scope. Corrections
  remain within that scope, and complete nonoverlapping member statements aggregate.
- Shared estimates take precedence over member estimates. Shared breakage totals allocate by
  SSP and replace member redemption estimates. Effective membership changes preserve earlier
  recognized revenue and use remaining SSP for supported prospective splits.
- Performing-entity agents retain supplier payables in the contracting entity and transfer
  only the net commission to the performer. This path requires aligned period dates.
- Foreign contract costs retain historical capitalization and clawbacks. Impairment uses
  independent functional recoverability; IFRS reversals remain capped by the independently
  measured unimpaired carrying amount, while ASC606 does not reverse impairment.

- Foreign return assets retain each delivery's original unit-cost estimate and FX rate.
  Recovery costs use the assessment-date rate; actual releases follow the existing
  FIFO/pro-rata policy. Later unit-cost estimates apply to later deliveries. Earlier
  deliveries without a cost estimate use the earliest retained estimate available for them.
- Foreign loss tests retain historical actual cost/revenue amounts and translate remaining
  original forecasts at the assessment-date rate. Journals, member balances and functional
  loss-register projections use that independent test. Reporting-currency snapshots use
  retained closing rates, with the period movement at the retained average rate.

## Contract-group separation and explicit limits

- Foreign fixed-service split continuation conserves original layer quantities and carrying
  across each destination. Rates, original source contracts and collection ages survive
  successive splits. Newly exposed gross liabilities restore historical credit carrying;
  monetary assets use split-date spot, with the difference shown as FX.
- Monthly group rollforwards show split reclassifications and FX separately and reconcile to
  native member endpoints. Member movements are unallocated; member endpoints remain visible.
  Current liability follows each destination's release layers and is apportioned by member
  liability carrying. Original source evidence and report cell links are retained.
- Contract-group separation also continues existing variable consideration, estimate-based
  recognition, returns/refunds, breakage, financing and noncash consideration. It preserves
  earlier revenue, original member ledgers and specialist balances; this does not transfer
  obligations or introduce new ASC606 treatments. Remaining service uses dated remaining SSP.
- Historical return entitlements stay with their delivery layers. Only future-delivery
  consideration enters redistribution; FIFO/pro-rata consumption and successive separation
  retain their distinct rates. Breakage and measured input/output progress price only remaining
  service. Cost recovery continues its existing cost cap or approved EAC method.
- Destination previews and journals use each member's original billing, revenue, refunds,
  financing and noncash components. Rollforwards include generated control-role movements.
  Reports retain group movements, member endpoints and original explanation/rerun evidence.
- Broader performing-agent calendars are not supported by the aligned-period implementation.
- Unsupported acquisition methods, agent acquisition attribution and broader entity/group
  combinations remain outside the completed reporting lane.

Focused checks accompany functional changes. Successful checks establish the exercised
behavior; they do not imply every possible contract scenario is supported. No deployment is
part of repository completion.
