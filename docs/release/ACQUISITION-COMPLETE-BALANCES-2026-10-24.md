# Complete nonposting acquisition balances — October 24, 2026

Evidence revision 44 closes the absent-member-balance-row reporting gap for a
single-member, principal, same-entity acquisition recomputed from inception in its
functional currency. A cutover beyond the ordinary measurement horizon now gets a
separate original nonposting balance observation. This supersedes the earlier
no-row refusal for newly computed versions meeting these conditions.

The native book loop repeats the original stages through costs with a separate
context whose measurement horizon reaches the cutover. It retains original calendar
states, policies and specialist inputs, uses a fresh memo and trace, and never runs
FX, posting or the ordinary output assembler in this supplementary pass. All
financial results of the ordinary pass remain authoritative. Sources have a distinct
subject namespace; dependencies and exact-companion references are preserved, so
the retained calculation chain can be replayed without replacing ordinary nodes.

The snapshot covers all 13 reported balance measures, including current parts,
refunds, deposits, consideration, cost assets and provisions. Each measured amount
must have its actual target and trace node. ERP-mode accounts receivable follows the
existing engine reporting default of zero, explicitly labelled unmeasured and
ERP-managed; it is not represented as an ERP-confirmed amount or a measured node.
Other missing or invalid component evidence is not filled with zero.

The report reader verifies the original files, selected version, book, member,
entity, currency, period, source nodes and amounts. It supplies a report balance row
without creating a financial database balance row. Before acquisition entry it adds
nothing; afterward it carries the original observation until another version is
selected. Contract balances, balance rollforward, currency translation, saved-source
reruns and acquisition cell explanations consume the same retained observation.

Necessary verification:
- A native case has no ordinary balance rows but retains a nonzero 100,000 receivable
  and 20,000 contract asset. Every observed node replays; ordinary nodes, postings,
  schedules and obligation versions equal revision 43. A changed observation amount
  is refused by the API reader.
- Public persisted-computation cases pass for the new no-row path, the previous
  closed-cutover path and old revision-43 named refusal. The new path covers all 13
  measures, three currency views, rollforward tie-out, source explanation, saved
  rerun and later-period carry-forward. A final check excludes the acquired contract
  before its cutover.
- Nine focused native/adapter cases and scoped Ruff/mypy checks pass.

Older versions without original observations still require a new computation;
report reads never manufacture historical evidence. Foreign-functional recomputation,
combined/multi-member and agent acquisition paths remain open. No deployment or
claim that the whole system is complete.
