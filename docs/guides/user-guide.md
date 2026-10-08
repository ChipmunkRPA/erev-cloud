# eRev Cloud user guide

This guide covers the words eRev Cloud uses, how money and dates travel through the REST API under `/api/v1`, and each area of the rail: Home, Contracts, Schedules, Close, Journals, Reports, Policies, Data, Approvals and Settings. Sandboxes and scenarios, AI assistance, the transition map for people coming from eRev desktop and the demo workspaces follow. The legacy migration itself is in the [migration guide](migration-guide.md); operations are in the [runbook](runbook.md); the controls a customer operates are in the [ITGC guide](itgc-guide.md).

What this guide describes is what the API and the built screens do at this revision. Where a specified screen or command is not built yet, the guide says so and names the API or the specification instead; it never describes a screen as present when the router has no route for it. Every in-app route named here (for example `/home`) exists in the web application's router; API paths are written with the `/api/v1` prefix. Permissions are named by their code; `GET /api/v1/permissions` lists them with their descriptions, and the roles that carry them are managed under Settings.

What release 1.0 does not do, where the product does less than its documents say, and what stands before production use are stated in [the limits of release 1.0](../release/LIMITS-1.0.md).

## Vocabulary

eRev Cloud uses its own terms (D-02). Screens, exports, messages and this guide use these words.

| Area | Term | Meaning |
|---|---|---|
| Navigation | Home | The starting workspace |
| Navigation | Contracts | Customer contracts and their versions |
| Navigation | Obligations | The performance obligations inside a contract |
| Navigation | Schedules | Revenue schedules by obligation and period |
| Navigation | Close | Period states and the close cockpit |
| Navigation | Journals | Journal runs and GL export |
| Navigation | Reports | Waterfalls, rollforwards, disclosures and audit evidence |
| Navigation | Policies | Revenue policies, SSP books and account mapping |
| Navigation | Data | Imports, integrations and the exception queue |
| Navigation | Approvals | Requests waiting for a decision |
| Navigation | Settings | Tenant, users, roles and developer settings |
| Amounts | Scheduled | Amounts whose recognition pattern is known |
| Amounts | Awaiting trigger | Amounts that wait for an event, such as delivery or acceptance |
| Amounts | Allocation adjustment | The difference between the allocated amount and the list amount |
| Balances | Contract liability | Consideration billed or due ahead of the revenue it pays for |
| Balances | Contract asset | A conditional right to consideration for goods or services already transferred |
| Balances | Unbilled receivable | An unconditional right to consideration that is not yet invoiced |

A contract's balance is always shown with its label, for example "Contract liability $1,200.00" or "Contract asset $300.00". The product never shows a signed position (D-12).

## Money and dates on the wire

These rules apply to every request and response of the REST API under `/api/v1`.

### Money (API-C-06)

- A monetary value is an object with a string amount and an ISO 4217 currency code:

  ```json
  {"amount": "12.30", "currency": "USD"}
  ```

- The amount carries exactly the currency's minor-unit decimals: `"1200"` for JPY, `"12.30"` for USD, `"1.250"` for BHD.
- Exact values and FX rates are strings with trailing zeros trimmed and no exponent, for example `"0.333333333333333333"` or `"1.0825"`.
- A JSON number in a money or decimal field is refused. The response is HTTP 422 with problem type `validation-failed`, and the offending field appears in `errors[]` with `rule_id` `API-C-06`.
- Posted amounts are rounded half up to the currency's minor unit (D-11).

### Dates and times (API-C-07)

- Business dates use `YYYY-MM-DD` and are read in the time zone of the owning legal entity.
- Timestamps use RFC 3339 in UTC with `Z`, for example `2026-01-01T00:00:00Z`.
- When a command supplies a timestamp `effective_at` instead of a business date `effective_date`, eRev Cloud converts it to the entity-local date before it assigns the period.

## Home

Route `/home`. Home shows, for the entity, period and book of the context pill, revenue against the prior period, contract liability, remaining performance obligations, the close status, open exceptions and pending approvals, each drilling to the screen that owns it; then the queues assigned to you, recent activity and your favourites. The figures come from `GET /api/v1/dashboard/home`; the notification bell reads `GET /api/v1/me/notifications` and `POST /api/v1/me/notifications/read-all`, and your notification preferences live under `/settings/notifications`.

"Search or run a command" in the top bar opens the command palette on every screen, as do Command K and Control K. The palette lists the pages and commands that match what you type. For a holder of `contract.read` it also finds records, from two characters on: contracts, customers, invoices, obligations and journal runs, read from `GET /api/v1/search` and grouped by kind; the chips above the list narrow the search to one kind, to pages or to commands. A record is found when every word you type begins a word of its two texts — for a contract its external id and its customer's name, for an invoice its number and its contract's external id. Enter opens the highlighted row: a contract at its obligations, a customer at its page under Settings, an invoice at the Billing tab of its contract, an obligation at its pane and a journal run at its page; with Command or Control held the row opens in a new tab and the palette stays open. "Show all results" opens the results page `/search`, which lists 25 records of each kind, adds the next 25 with "Show more" and keeps the text and the Scope filter in its address, so a list of results can be sent as a link.

On a workspace whose accounting policy set is the legacy-parity preset, Home also shows the dismissible panel "Coming from eRev desktop" (dismissal is per device). Its map is the section [Coming from eRev desktop](#coming-from-erev-desktop) below; the dedicated help screen for the map is not built at this revision.

Sign-in is `/sign-in` (password, then the authenticator code); a person who belongs to several workspaces chooses one on `/select-workspace`. Every workspace is either a production workspace or a sandbox; the kind is shown in the shell and can never change.

## Contracts

Routes `/contracts` (list with filters, saved views and quick lists), the draft contract form at `/contracts/new` and `/contracts/:contractId/edit`, and the contract workbench `/contracts/:contractId` with its tabs `/contracts/:contractId/obligations`, `/contracts/:contractId/estimates`, `/contracts/:contractId/schedules`, `/contracts/:contractId/billing`, `/contracts/:contractId/journals`, `/contracts/:contractId/modifications` and `/contracts/:contractId/history`. The Estimates tab lists the contract's estimated elements; a version of an element is prepared in a drawer with its impact preview, submitted for approval and, while it waits, withdrawn. The Modifications tab lists the contract's modifications; a new one is prepared in the five steps of the wizard at `/contracts/:contractId/modifications/new` (change, questionnaire, treatment, impact preview, submission), and one that is no longer a draft is read at `/contracts/:contractId/modifications/:modificationId`. The History tab shows the contract's activity (changes, approvals and, under "Calculations", the system's computations), its versions with a field-by-field comparison of two of them and, for a holder of `audit.read`, its audit trail. The API below serves the same data.

A contract moves through the statuses `DRAFT`, `PENDING_REVIEW`, `ACTIVE`, `COMPLETED`, `TERMINATED` and `VOIDED`; a document that fails the contract criteria is `NOT_A_CONTRACT`. The API under `/api/v1/contracts`:

- Create a draft with `POST /api/v1/contracts` and replace it with `POST /api/v1/contracts/{contract_id}/replace-draft`; `GET …/activation-checklist` shows what activation still needs; `POST …/submit-activation` sends the contract for approval (subject `CONTRACT_ACTIVATION`), and the approver must be someone other than the submitter.
- Read the figures: `GET …/allocation`, `GET …/balances` (labelled balances, never a signed position), `GET …/schedule`, `GET …/subledger-lines`, `GET …/sources` (the source records behind the contract), `GET …/history` and the immutable versions `GET …/versions`, `GET …/versions/{version_no}` and `GET …/versions/compare`.
- Record what happened: `POST …/events` (deliveries, billings, acceptances, price changes and the other event kinds; `POST …/events/preview` shows the effect first), `GET …/events`; an event can be voided only through `POST /api/v1/events/{event_id}/request-void` with approval. A delivery, progress, milestone, cost or return event that a signed-in person records is not appended at once: the answer names an event submission and its approval request, a user other than the preparer holding `event.approve` approves it, and the events are then appended and the contract computed. Progress, milestone, cost and acceptance events need at least one evidence file (`evidence_file_ids`), which is attached to the request. `GET /api/v1/event-submissions` lists what waits, and `POST /api/v1/event-submissions/{submission_id}/withdraw` takes a submission back. If the contract changed meanwhile so that the events no longer fit — for example another delivery used up the remaining quantity — the approval voids the request as stale and the preparer records the events again. Events an API client sends are appended directly. Give a usage report or a royalty statement the last day of its usage period as its date: one whose usage period ends after its date is refused (`USAGE_PERIOD_NOT_ENDED`), and one dated in a later accounting period than the one its usage period ends in puts the fee's revenue into that later period.
- Estimates: `GET|POST …/estimates`, then versions under `/api/v1/estimates/{estimate_id}/versions` with `preview`, `submit` and `withdraw` on `/api/v1/estimate-versions/{version_id}`.
- Holds and memos: `POST …/apply-hold`, `POST …/release-hold`, `POST …/update-memos`.
- Void a contract with `POST …/request-void` and a reason: nothing is deleted; reversal lines post in the first open period after approval (subject `CONTRACT_VOID`).
- Obligations: `GET /api/v1/obligations/{obligation_id}` with `events`, `schedule`, `versions` and `material-right`; `POST …/request-ssp-override` and `POST /api/v1/contracts/{contract_id}/obligations/{obligation_key}/distinct-review` for the two judgements that need a reviewer.
- Contract combinations: `GET /api/v1/combination-suggestions`, `POST /api/v1/combination-groups` and `POST /api/v1/combination-groups/{group_id}/submit`; judgement records under `/api/v1/judgements`.

Every computed figure links to a calculation trace: `GET /api/v1/calc-traces/{trace_id}`, shown at `/trace/:calcTraceId`, and the Explain reads `GET /api/v1/explain/{object_type}/{object_id}/{measure}` with `POST …/verify` to recompute the figure from its inputs. Explain is deterministic and is not AI.

## Schedules

Route `/schedules`: revenue by period for the context entity, period and book. The screen runs the report "Revenue waterfall" (rows by contract, obligation, product or revenue category; by month, quarter or year) and has a second layout, "Lines", of the revenue schedule lines by obligation and period. It lists revenue lines only; the lines of the other schedule kinds, among them the amortization of contract cost assets (`COST_AMORTIZATION`), are read through the API with `schedule_kind`. The API is `GET /api/v1/schedule-lines` (filters, sorting and cursor paging as every list), `GET /api/v1/contracts/{contract_id}/schedule` and `GET /api/v1/obligations/{obligation_id}/schedule`. A line is Scheduled when its recognition pattern is known and Awaiting trigger when it waits for an event such as delivery or acceptance (see Vocabulary).

## Close

Route `/close` redirects to the close cockpit of the context period, `/close/:entity/:book/:period`; `/close/:entity/:book/:period/journal-preview` previews the journals of the period before a run.

### Close and lock

A period is `FUTURE`, `OPEN`, `CLOSING`, `CLOSED`, `REOPENED` or `PERMANENTLY_LOCKED`. The commands are under `/api/v1/periods/{period_id}`:

- `GET /api/v1/periods` and `GET /api/v1/periods/{period_id}`; `GET …/cockpit` (the gate results), `GET …/transitions` (who moved the period and when) and `GET …/checklist` (the close checklist items, from the templates under `/api/v1/close-checklist-templates`).
- `POST …/open` opens a future period; `POST …/start-close` moves an open period to `CLOSING`, where only holders of `period.lock` may submit manual adjustments for the period; `POST …/cancel-close` ends the soft close and returns the period to the state it started from: `OPEN`, or `REOPENED` for a period that has been locked before, where postings keep needing a second person's approval.
- `POST …/checklist/{item_id}/sign` and `POST …/checklist/{item_id}/waive` (a waiver needs a reason).
- `POST …/request-lock` submits the lock (subject `PERIOD_LOCK`); a second holder of `period.lock` approves it — the submitter never locks alone. The lock gates are the ones of the cockpit: interface batches complete, journals balanced and complete, no pending approval affecting the period, exceptions resolved, waived or dismissed, batches acknowledged, reconciliations reviewed, judgements reviewed, open holds released or waived, data-quality findings of severity `ERROR` cleared, the period's close run completed, and every checklist item signed or waived. A data-quality finding that has been corrected clears itself: the monitors run before `start-close` and `request-lock`, in the close run and every night, and resolve an exception whose condition they no longer find (shown as resolved by the system). A waiver request that is still pending for such an item is not approved any more: the item it asked to waive is no longer open, so the request is voided when someone decides it (`stale-approval`). A finding that is still there is cleared only by an approved waiver. The close run is a gate that cannot be waived: run the close before the request ("Close run not completed"), and run it again when the gate reads "Close run out of date, run it again: <n> contracts" — after the run, contracts were changed in a way that leaves a period-end amount of the period still to post (a late event dated in the period, for instance; work recorded for a later period does not put the run out of date). Run it again too when the gate reads "Close run out of date, run it again: exchange rates changed since it ran. A run posts nothing where the change moves nothing for this entity." — or "policies", or both: an exchange rate dated in the period or earlier was replaced after the run, or a policy value set per period came into force after it and on or before the period's last day (a value that comes into force after the period belongs to a later period and asks for nothing); the new run posts the difference to the period-end amounts, or nothing. The approval of a rate set version also marks the contracts its changed rates reach as changed; the run's "Recompute changed contracts" step recalculates them first, so revenue translated at a corrected average or spot rate is posted before the lock. Locking freezes the twelve lock snapshots and, when needed, moves the next period from `FUTURE` to `OPEN`, so a late event always has a first open period. Periods lock in order: the request, and the approver's decision, are refused with `earlier-period-open` while an earlier period of the entity and book is open, in soft close or reopened (BR-CLS-08) — lock the earlier period first. Periods also open in order: a future period does not open while the period before it is still future.
- `POST …/request-permanent-lock` asks for a closed period to become `PERMANENTLY_LOCKED`, once every earlier period of the entity and book is. Only a holder of `period.lock` for the entity (a Controller) requests it, and a second Controller approves it — the requester cannot. Such a period never reopens.
- `GET …/locks` lists the lock and reopen records, newest first.

The period evidence pack generated at lock (report code `period_evidence_pack`, output ZIP) is described under Reports; the reopen procedure follows.

### Manual adjustments

A manual adjustment changes one contract's accounting by hand, under maker-checker (REQ-JE-019, REQ-REC-023). No screen is built for it at this revision: the commands are under `/api/v1/manual-adjustments`, and its requests are decided on `/approvals`.

- **Kinds.** `MANUAL_RELEASE` and `MANUAL_DEFER` move an amount of one obligation into or out of the period: an `amount`, a `ratio` of what remains, or `remaining`. `SCHEDULE_OVERRIDE` states the revenue of the periods it lists. `MANUAL_JOURNAL` and `ACCOUNT_RECLASS` carry lines that balance, each with an account role, a GL account and a signed amount (a debit positive, a credit negative).
- **Prepare.** `POST /api/v1/manual-adjustments` with the kind, the contract, the effective date, a reason code, a memo and the payload of the kind creates a draft (`adjustment.create`). The server derives the absolute amount in the entity's functional currency (`amount_functional_abs`) from a dry run; it is never sent. `PATCH /api/v1/manual-adjustments/{id}` with `If-Match` edits a draft, `POST …/{id}/preview` answers 202 with a job whose result is the impact summary, and `POST …/{id}/discard` with a reason voids a draft that is no longer needed. Lines that do not balance are refused with 422 `ledger-unbalanced`. Only the person who created an adjustment can edit it, as a draft or after a rejection: anyone else is refused with 403 and "Only <creator> can change this adjustment.", so nobody approves content they wrote. A colleague with `adjustment.create` can still submit or discard the draft — a draft whose creator is away never holds a close — and neither the creator nor the person who submitted it can approve it.
- **Submit.** `POST …/{id}/submit` routes the adjustment to a holder of `adjustment.approve`; neither the person who prepared it nor the person who submitted it can approve it. From USD 10,000.00 the adjustment needs an attachment (`POST /api/v1/attachments`, subject type `manual_adjustment`) and a Controller decides a second step. While the period is `CLOSING`, only holders of `period.lock` submit.
- **Pending adjustments change nothing.** Until it is approved an adjustment changes no schedule and no balance, and a draft or submitted adjustment of the period holds the lock gate "Manual adjustments cleared". `POST …/{id}/withdraw` takes the request back and the adjustment is a draft again; a rejected adjustment returns to draft when it is edited.
- **Approval.** The approval records the event `MANUAL_ADJUSTMENT_APPLIED` on the contract, posts the lines of a journal or reclassification on the accounts approved and recalculates the contract. The adjustment survives later recalculations, and a journal run shows its lines as a manual entry that names the adjustment.
- **Correcting a posted adjustment (known limitation).** A posted adjustment cannot be voided or reversed in this release. `POST /api/v1/events/{event_id}/request-void` refuses the event `MANUAL_ADJUSTMENT_APPLIED` with 409 and "A posted manual adjustment cannot be voided. Correct it with a further adjustment." Prepare a further adjustment that carries the correction; both stay in the register, each with its preparer and approver.
- **Defer past lock.** `POST …/{id}/request-defer-past-lock` with a comment replaces the pending request by a request to defer the adjustment. Once that is approved the adjustment no longer holds the lock. Submit it again when it is ready: after the lock it posts in the first open period and keeps its own period as origin. A rejected deferral leaves the adjustment pending.
- **Register.** The report `manual_adjustment_register` lists every adjustment with its preparer, approver, amount, attachments and whether it was deferred past lock.
- **Limits in this release.** A manual journal or reclassification is available for a contract in its entity's functional currency; for another contract it is refused by name, and a release, a deferral or a schedule override is not limited. An adjustment applies in the book it names (default the primary book); a second book of the entity is adjusted by an adjustment of its own.

### Reopen a period

A `closed` period reopens only through an approved `PERIOD_REOPEN` request (SM-07; REQ-CLS-011).

### Request the reopen

`POST /periods/{id}/request-reopen` with `reason_code` (`ERROR_CORRECTION`, `LATE_SOURCE_DATA`,
`AUDIT_ADJUSTMENT` or `OTHER`) and a comment of at least 10 characters; `If-Match` carries the
period's version. The request is refused with `later-period-closed` while a later period of the
entity and book is `closed` or `permanently locked` (BR-CLS-05): reopen the later period first. A
`permanently locked` period never reopens.

For `ERROR_CORRECTION`, select an existing reviewed **Estimate vs error** judgement before
requesting the reopen. It must belong to a contract of the same entity and apply to the period's
book or all books. The form shows its conclusion and reviewer. If none is available, prepare
the judgement and complete its independent review first. The API requires its
`judgement_record_id`; other reopen reasons must omit this citation.

The request retains the submitted conclusion and review evidence. Approvers can read it on the
approval page, and the completed reopen retains the citation in close history. A superseded or
changed judgement makes the request stale; submit a new request with current reviewed evidence.
Readers must still have access to the request's content to see that evidence.

### Two approvers, at least one Controller

Two people holding `period.reopen_approve` decide the request, each with a fresh authenticator
code; at least one is a Controller, and neither is the requester. Two Revenue Reviewers leave the
request pending; a second decision by the same approver is refused (`approver-already-decided`).
On the second qualifying approval the period is `reopened`, a `REOPEN` lock record names the lock
it reopens, the lock snapshots stay, the period's reconciliations move to `REOPENED`, and the
Controllers, Revenue Reviewers and Auditors with the entity in scope are notified.

### Posting into a reopened period

Every posting into a reopened period — an import, a manual event, a manual adjustment or a journal
run — needs a human approval by someone other than the submitter; auto-approval rules do not apply
(BR-CLS-06). The committed subledger lines carry `is_post_reopen = true`. That holds until the period is
locked again: a line posted while the reopened period is in soft close — the close run's
period-end entries, an adjustment — is flagged as well.

### Re-lock and the diff report

Start the close again, pass the gates and request the lock as for any period. The re-lock writes a
new `LOCK` record whose `previous_lock_id` names the `REOPEN`, freezes the twelve snapshots again and
stores a diff report (`diff_report_file_id`) comparing the previous lock with the new one: both lock
ids and manifests, each snapshot kind's hashes and row counts, the rows added, removed or changed by
row key with their previous and current values, and the certification before and after
(BR-CLS-07). `GET /periods/{id}/locks` lists every record, newest first.

## Journals

Routes `/journals` (journal runs), `/journals/runs/:runId` with `/journals/runs/:runId/lines` and `/journals/runs/:runId/batches`, and `/journals/entries` (entries by date range). A journal run is calculated for one entity, book and period with `POST /api/v1/journal-runs` (`journal.run`); `GET /api/v1/journal-runs/{run_id}` with `summary`, `entries`, `lines` and `batches` shows it; every batch balances. A line drills back to its subledger lines with `GET /api/v1/journal-lines/{line_id}/drill`, and a posted batch to its acknowledgement with `GET /api/v1/journal-batches/{batch_id}`.

### Export journals

An approved journal run leaves eRev Cloud as balanced journal entries for your general ledger (REQ-JE-011 to REQ-JE-013).

### Approve a run

- Submit a calculated run with `POST /api/v1/journal-runs/{id}/submit`. A holder of `journal.approve` approves it on `/approvals`; the approver can be neither the user who submitted the run nor the user who calculated it.
- Approval moves the run and every batch to Approved and writes the export of each batch.
- Cancel a run that is not exported yet with `POST /api/v1/journal-runs/{id}/cancel` and a `reason`. A pending approval request is voided.
- A period that is Closed or Permanently locked takes no journal run and gives none up: calculating a run for it, or cancelling one of its runs, answers 409 `period-closed`. Reopen the period first. A period that is not open yet takes no journal run either: 422 on `period_key`, "<period> is not open yet for <entity> in book <book>. Open the period before running journals."
- A journal run is made only when there is something for it to summarize, or when the period has no run yet. Where a run that is not cancelled stands and a new one would have no line, `POST /api/v1/journal-runs` answers 409 `invalid-transition`, "Journal run <run> is the latest run of <period> for <entity> in book <book>, and there is nothing for a new run to summarize." That is not the statement that the period is journalised: the lock gate for journal completeness says that. If the gate names a posting as held, release the journal-export hold and calculate again. If it names a posting as uncovered that a run left out while its contract was on hold, calculate again — Run journals, or Run close: the next run takes the released posting over, whether or not the earlier run has been exported. Otherwise nothing is to be done; cancel the run first only if you want to calculate the period again. The first run of a period without activity is made empty — no lines, no batches. It is not submitted for approval ("Journal run <run> has no journal lines: there is nothing to approve."), and the period locks on it as it stands.
- Cancel the latest run first. When a later run of the same entity, book and period stands, the earlier one answers 409 `invalid-transition`: "Journal run <run> was calculated after this run for the same entity, book and period. Cancel <run> first." A new run always continues where the earlier runs end, so an earlier run cancelled on its own would leave its activity in no journal.
- A run cannot be cancelled while one of its batches is being sent to the ledger: 409 `invalid-transition`, "An export of this journal run is in progress: batch <batch> is being sent. It cannot be cancelled while a batch is being sent. An interrupted export resumes about 15 minutes after it stopped." The export always completes first. An Exported batch puts the run past cancelling; the run of a Failed batch is cancelled only after eRev asked the ledger (see the two more ways on, below).
- Nor can it be cancelled while a batch waits to be sent again after a failed attempt: 409 `invalid-transition`, "An export of this journal run is in progress: an attempt to send batch <batch> failed and it will be sent again. It cannot be cancelled until the batch has been sent or has failed." The ledger may have taken the batch although its answer never arrived. The next attempt asks the ledger first. Once the batch is Failed, cancelling the run asks the ledger too (see the two more ways on, below).

### Export and download

- Holders of `journal.export` export an approved run with `POST /api/v1/journal-runs/{id}/export`. It answers 202 with a `JOURNAL_EXPORT` job and its `Location`. Repeating the command returns the existing export records and never posts a batch twice.
- A batch exports through the adapter it was calculated for. Naming another `adapter` answers 422 `validation-failed`.
- With `CSV` the batch becomes Exported once its file is written. Download it with `GET /api/v1/journal-batches/{id}/download`: a ZIP that holds the CSV and a JSON manifest.
- The CSV has one row per journal line, with the columns `posting_period`, `entity`, `currency`, `je_id`, `external_id`, `account`, `debit`, `credit`, `dimensions` (JSON), `memo`, `source_references`, `functional_currency`, `debit_functional` and `credit_functional`. The source references name the legacy key or contract, the journal line id for drill-back and the number of detail lines. Amounts are raw values at the currency's minor unit, and text that a spreadsheet would evaluate starts with an apostrophe.
- `currency`, `debit` and `credit` are the contract's transaction currency and amounts; `functional_currency`, `debit_functional` and `credit_functional` are the entity's own currency and the amounts eRev measured in it. For a contract in the entity's currency the two pairs are equal. A foreign-currency remeasurement has no transaction amount: its row shows 0.00 / 0.00 in the transaction columns and the amount in the functional columns. Book the functional columns in a ledger kept in the entity's currency.
- The manifest holds `row_count`, `totals` with the transaction `debit` and `credit`, `totals_functional` with the functional ones, and `sha256`, the SHA-256 of the CSV bytes. Check the hash before you import the file.
- The external id `erev:<workspace code>:<run no>:<batch no>:<chunk no>` identifies the batch in your ledger. Import each file once.
- Record the ERP reference: after you import a CSV batch, confirm it with `POST /api/v1/journal-batches/{id}/acknowledge` and the ledger's document number in `gl_document_id` (required), with `gl_posted_date` and a `message` if you wish. The batch becomes Acknowledged, and so does the run once every batch is. Only an Exported batch can be acknowledged. A batch that is not acknowledged keeps the period from locking ("Unacknowledged batches").
- When the ledger or the adapter refuses a batch, the batch is Failed and shows the refusal in `last_error`; the exporter and the Controllers whose role covers the batch's entity receive "Journal export failed: <run>", and the Exceptions list holds an item `JOURNAL_EXPORT_FAILED` for the batch. Correct the cause, then send the batch again with `POST /api/v1/journal-batches/{id}/retry` (202 with a `JOURNAL_EXPORT` job). A retry never posts a batch twice: the batch keeps its external id, and the ledger is asked for the posting first. Only a Failed batch can be retried, and not while it is still being sent: an interrupted export resumes by itself about 15 minutes after it stopped, and a retry before that answers 409. A batch that is already waiting to be sent again keeps its time: a retry does not send it earlier.
- When the ledger can never accept a batch as it was generated, there are two more ways on. If no batch of the run has reached a ledger, cancel the run (`POST /api/v1/journal-runs/{id}/cancel` with a reason): eRev first asks the ledger whether it holds the failed batch after all — if it does, the batch is Acknowledged and the run is kept; if not, the run is Cancelled and you calculate the period again. If part of the run is already in the ledger, hand the failed batch over (`POST /api/v1/journal-batches/{id}/hand-over`): download its file, post it by hand and record the ledger's document number as for a CSV batch. Both ways wait until the ledger has had its time. For 15 minutes after an attempt the ledger did not refuse — it did not answer, or eRev could not complete the export — the cancel and the hand-over answer 409 and say how many minutes are left; a retry is taken at once. And a batch the ledger accepted without showing it yet is neither cancelled nor handed over, however long ago: retry it — the retry asks the ledger first and records the document as soon as the ledger shows it. A batch whose lines changed after its approval is refused in every direction — it is not sent, not handed over and not downloaded.
- Webhook endpoints subscribed to `journal_batch.exported` and `journal_batch.acknowledged` receive one delivery when a batch is exported and one when it is acknowledged, with the ids and links of the batch and its run. A refused batch sends neither.
- Sandbox workspaces never export journals. The export command answers 403 `sandbox-restricted` with "Sandbox workspaces cannot post or export journals.", and the CSV download still works (REQ-PLT-022).

### Export to NetSuite or QuickBooks Online

- A run goes to the general ledger connection of its entity: the one active connection that takes journals (NetSuite, QuickBooks Online or CSV; direction outbound or both) and covers the entity. The ledger is fixed when the run is calculated; without such a connection the run is CSV. To send a calculated run somewhere else, cancel it and calculate it again.
- When more than one active connection covers the entity, the calculation is refused: "<entity> has more than one active general ledger connection (<codes>). Disable all but one before calculating journals."
- A large batch is sent in chunks: NetSuite 500 lines, QuickBooks Online 250, or the connection's `max_lines_per_chunk` (a whole number of at least 2). Each chunk is a batch of its own, with whole journal entries and an external id that ends in the chunk number. An entry larger than a chunk is split by contract. If one contract's part of an entry is still larger than a chunk, the calculation is refused and names the contract; raise the connection's chunk size.
- A batch is sent in the entity's functional currency, with the amounts eRev measured in that currency; for a contract in another currency, that currency and its amounts go along for information only. Both lines of a foreign-currency remeasurement therefore reach the ledger, and revenue and contract balances arrive at the rates eRev measured them at, whatever rates the ledger holds.
- For whoever runs the ledger: the accounts eRev posts to carry these balances in the functional currency only, the transaction-currency detail stays in eRev, and the ledger must not revalue those accounts itself — eRev's remeasurement is the only one.
- When the ledger accepts a chunk, its document number is recorded on the batch and the batch is Acknowledged; no manual confirmation is needed. A chunk the ledger reports it already holds is recorded as a duplicate with the ledger's document. Nothing posts twice.
- If the connection was disabled or removed before a batch is sent, the batch is Failed with "General ledger connection <code> is disabled. Enable it, then retry the batch." or "The batch's general ledger connection no longer exists." Nothing is sent.
- When the ledger asks the sender to wait (HTTP 429 with `Retry-After`), the next attempt is made no earlier than it asked.
- In this release the NetSuite and QuickBooks Online adapters are delivered against the built-in mock servers of development, test and demo environments (REQ-JE-014, REQ-JE-015) and send no credential. Production workspaces export by CSV.


## Reports

Route `/reports` is the catalogue; `/reports/:reportCode` opens one report with its parameters, the run history and the outputs. The tab "Report runs" at `/reports/runs` is the register of every report and export run the viewer may see, and `/reports/runs/:runId` opens one run; the tab "Audit log" at `/reports/audit-log` lists the audit events under the latest verification of their chain, which `/reports/audit-log/verifications/:verificationId` opens. The specified evidence-pack and scenario tabs of the Reports area are not routed at this revision; their data is available through the API described here.

### Report runs

Every report you open or export is a report run: a stored, numbered record that an auditor can rely on (REQ-RPT-002).

### Definitions

- `GET /api/v1/report-definitions` lists the standard reports. Tenants cannot change a definition; a changed definition becomes a new version.
- Each definition names its parameters in `parameters_schema`, its output formats and its tie-outs.
- Holders of `report.export` also receive `ipe_logic`: the source tables, joins, filters, parameters and definition version, for the auditor's file (REQ-RPT-027).

### Running a report

- `POST /api/v1/report-runs` with `report_code`, `parameters` and `output_format` answers 202 with the job, the job's `Location` and the run id in `X-Erev-Report-Run-Id`. JSON runs need `report.run`; `XLSX`, `CSV` and `PDF` runs need `report.export` as well.
- A parameter the definition does not declare, or a start period after its end period, answers 422 `validation-failed`.
- A period key such as `FY2026-P09` belongs to a fiscal calendar and is read in each entity's own. A run over entities that keep different fiscal calendars is therefore refused when it names a period by key, and the revenue waterfall and the disaggregation over them also without one, because their columns are period keys: 422 `validation-failed` with the rule `CALENDARS_DIFFER` and "The entities of this run keep different fiscal calendars, so a period key can name different months for them. Run the report for entities of one calendar." Choose one entity, or entities of one calendar. Any other run that names no period reads each entity at its own period holding the run's date.
- The run stores every parameter, including the defaults eRev Cloud filled in: `entity_codes` defaults to every entity in your scope and `known_at` to the time of the request.
- `GET /api/v1/report-runs/{id}` shows the run record: run number, report and version, every parameter, entity scope, `known_at` or lock, engine release, user, start and finish times, row count, control totals, tie-out results, ledger heads and the output SHA-256.
- `GET /api/v1/report-runs/{id}/data` pages the rows of a JSON run, for example 200 rows a page with `limit=200` and `next_cursor`.

### Outputs

- `GET /api/v1/report-runs/{id}/output` streams the output as a download and records a `report.export` audit event with the run id.
- XLSX outputs open with a header block: report name and version, run number, entity, book, as of, source, engine release, user, UTC run time, row count, output SHA-256, every parameter and the control totals. Amounts are numeric cells formatted with the workspace's negative number style.
- CSV outputs use raw values (`-4000.00`, `2026-09-07`, UTC timestamps) and ship a JSON manifest with `row_count`, `control_totals` and `sha256`, the SHA-256 of the CSV bytes. Download it with `?part=manifest`.
- PDF outputs print the same stamp on the first page, and every page footer reads "Run <run no> · page <n> of <m>".
- Text that starts with `=`, `+`, `-`, `@`, a tab or a carriage return is written with a leading apostrophe in CSV and XLSX, so a spreadsheet never evaluates it as a formula. Numbers stay numbers (REQ-SEC-011).
- For JSON and CSV runs the output SHA-256 is the hash of the file. XLSX and PDF files carry their own run number and time, so their printed SHA-256 is the hash of the run's JSON dataset.

### Reproducing a run

`POST /api/v1/report-runs/{id}/rerun` creates a new run with identical parameters, entity scope and `known_at`. When its job finishes, the job result shows `output_sha256_equal` and `control_totals_equal`. Both are `true` when the source data has not changed.

A failed run keeps its record with status Failed and the problem that stopped it.


### Data extracts

The nine extracts are CSV datasets with a JSON manifest for BI tools (REQ-RPT-028), run like any report with `POST /api/v1/report-runs` and downloaded from `GET /api/v1/report-runs/{id}/output` (`?part=manifest` for the manifest). Parameters: `mode` `FULL` (every row as of the source time: the lock of the context period when it is locked, else now, through `period_lock_id` or `known_at`) or `INCREMENTAL` (rows created — recorded, for events and subledger lines — after `known_since` and at or before the source time); `entity_codes` and `book` from the context (`book` is absent for `extract_contracts` and `extract_events`). Values follow the CSV rules above; columns holding personal data are never added. The manifest carries `dataset`, `schema_version`, `mode`, `known_since`, `known_at`, `period_lock_id`, `row_count`, `control_totals` and `sha256`.

Dataset schemas, version 1 (the table ids are those of the data model, `docs/04-DATA_MODEL.md`):

| Code | Rows | Columns | Control totals |
|---|---|---|---|
| `extract_contracts` | Contracts in scope (T-CON-01) | Every column of the contract table except `tenant_id`, in table order, plus `customer_code`, `contracting_entity_code`; `custom_attributes` as canonical JSON | `row_count` |
| `extract_obligations` | Obligation versions of the latest contract version per book known at the source time (T-CON-11) | Every column except `tenant_id` and `trace_nodes`, plus `contract_external_id` | `row_count`; `allocated_amount` and `revenue_cum` sums per currency |
| `extract_contract_versions` | Contract versions known at the source time (T-CON-08) | Every column except `tenant_id`, plus `contract_external_ids` (member contracts) | `row_count` |
| `extract_schedule_lines` | Schedule lines of the latest versions (T-ENG-02) | Every column except `tenant_id`, plus `contract_external_id`, `period_key` | `row_count`; `amount` sum per currency |
| `extract_subledger_lines` | Subledger lines recorded at or before the source time (T-SL-04) | Every column except `tenant_id`, plus `contract_external_id`, `period_key`, `origin_period_key`, `gl_account_code` | `row_count`; `amount_functional` sum per functional currency (0.00 per entity, book, currency and period) |
| `extract_journal_lines` | Journal lines of non-cancelled runs (T-SL-09) | Every column except `tenant_id`, plus `je_no`, `run_no`, `batch_external_id`, `period_key` | `row_count`; `debit_functional` and `credit_functional` sums per functional currency |
| `extract_balances` | Balances of the latest versions (T-CON-09) | Every column except `tenant_id`, plus `contract_external_id`, `entity_code` | `row_count`; `contract_liability_functional`, `contract_asset_functional`, `unbilled_receivable_functional` sums per currency |
| `extract_events` | Contract events recorded at or before the source time (T-CON-05) | Every column except `tenant_id`; `payload` as canonical JSON | `row_count` |
| `extract_legacy_contract_live` | Legacy history rows over all dates (04 §17.1 rule 1) | The 71 legacy `Contract_Live` columns of 04 §17.2, in legacy order, with the legacy export format rules | `row_count` |

Status at this revision: the nine definitions are in the report catalogue (`GET /api/v1/report-definitions`), but no builder is registered for them, so a run of an extract does not produce output yet; the schemas above are the contract the builders will meet. Parquet extracts are a later release.

### Evidence packs

The period evidence pack (report code `period_evidence_pack`, kind `PACK`, output ZIP; one entity, book and period, at a lock) collects the close certification, the lock snapshot ids and hashes, the journal batch register with its balancing and completeness results, the reconciliations with their sign-offs, the rollforwards, RPO and disaggregation, the manual adjustment, modification, SSP and configuration registers, the late-entry and out-of-period reports, the user listing and the separation-of-duties report as of period end, and the audit chain verification, each file with its SHA-256 in the manifest (REQ-RPT-014). The contract sample pack (`contract_sample_pack`; ZIP, PDF or XLSX) does the same for a sample of contracts as of a date (REQ-RPT-015). Downloading a pack needs `evidence.export`. Status on October 8, 2026: retained first-close packs can be read and downloaded through the API. Public creation and listing, automatic generation on lock, contract samples, change/access packs and re-lock variance are still pending; the report-catalogue PACK builders are not available. The first-close worker and transactional creation command exist internally.

For an existing first-close pack id, `GET /api/v1/evidence-packs/{id}` returns its status, manifest and separately retained `manifest_sha256`. A completed pack has a `download_href`; `GET /api/v1/evidence-packs/{id}/download` verifies the saved ZIP and its retained sources before returning it. A queued or failed pack cannot be downloaded. Each successful download records `evidence.export` with the pack id. Header reads require `report.run`, `audit.read` and `contract.read`; downloads additionally require `report.export` and `evidence.export`, with current access to the relevant entities and source records. A changed or inconsistent file is refused. Generic `/files` routes do not serve pack content or metadata.

The audit log is read with `GET /api/v1/audit-events` (`audit.read` for all entities: an audit event carries no entity); `POST /api/v1/audit-events/verify` verifies the hash chain, for all entities too, and `GET /api/v1/audit-events/verifications` lists past verifications to any holder of `audit.read`.

## Policies

Route `/policies` redirects to `/policies/revenue`; the tabs are `/policies/control-rules`, `/policies/accounting`, `/policies/ssp-books`, `/policies/ssp-calculator` and `/policies/account-mapping`. Every configuration object is versioned and follows one lifecycle: a `DRAFT` version is authored (`config.author`), tested where the object has a test command, submitted, and published by an approver other than the author (`config.approve`); reads need `config.read`.

- Revenue and accounting policies: `GET /api/v1/registry/parameters` is the parameter catalogue; versions live under `/api/v1/policies` with `submit`, `publish`, `withdraw` and `test`; `GET /api/v1/policies/resolve` answers the value in force for a scope. `POST /api/v1/policies/presets/legacy-parity` creates the `DRAFT` legacy-parity version of the accounting policy set (see the migration guide).
- Control rules: rule sets and versions under `/api/v1/rule-sets` and `/api/v1/rule-set-versions/{version_id}` with `rules`, `lint`, `test`, `test-cases`, `submit` and `publish`; `POST /api/v1/rule-sets/{rule_set_id}/evaluate` evaluates a version against a case. An approval-routing rule adds steps to an item type's own approval and never lowers it, and an auto-approval rule covers only what an integration originates (contract activations whose every event an integration wrote, import commits an API client uploaded) — the legacy SSP replay of a migration and the setup grants are approved only by the rule sets each workspace is provisioned with; a rule without a condition, one that would lower an approval, or one whose condition cannot be evaluated on its field (an ordering or a prefix on a list such as `flags`, a value of another type) is refused when it is saved and again at publication.
- Obligation templates: `/api/v1/pob-templates` and `/api/v1/pob-template-versions/{version_id}`.
- SSP books: `/api/v1/ssp-books`, versions with `entries`, `diff`, `submit` and `withdraw`; the SSP calculator runs under `/api/v1/ssp-calculator-runs` with `observations`, `exclusions`, `results` and `create-draft-version`; `GET /api/v1/ssp/resolve` answers the SSP in force. A draft version made from a run copies the approved version and replaces the band of every product the run studied; each entry keeps its value basis and quantity unit. A study states a price per unit of line quantity, so the draft is refused — the message names the product, and nothing is written — for an entry priced per increment of a service unit or as a percentage of list price, and for a series product the approved version holds no entry of: start a run without that product. A study does not compare booked terms: for an entry priced for its booked term (`PER_BOOKED_TERM`) it takes sales of different terms as they are.
- Account mapping: `/api/v1/account-mappings` versions with `rules`, `test`, `submit` and `publish`; `GET /api/v1/account-mappings/resolve` answers the account for a role.
- Judgement records (`/api/v1/judgements`) are submitted for approval the same way. Policy overrides for one contract or one obligation are not offered in release 1.0: no screen requests one, and `POST /api/v1/policy-overrides` refuses the request and says what decides the parameter instead — the policy registry for the workspace or a legal entity, the product or its obligation template, or a record of the contract such as an estimate version or a reviewed judgement record. The policies screens keep printing the levels "Contract" and "Obligation" of a parameter as the registry lists them; in this release no value is set at them.

## Data

Routes `/data/imports` (list), `/data/imports/new` (the import wizard), `/data/imports/:importId` (the steps), `/data/templates` (template downloads) and `/data/exceptions` (the exception queue with its item pane). A migration is opened at `/data/migrations/:migrationId`; the migrations list and the new-migration screens are not routed at this revision (start a migration through the API, see the migration guide). Integrations are the tab "Integrations" of this area, for a holder of `integration.manage`: `/data/integrations` (the connections), `/data/integrations/:connectionId` (one connection with its settings, its sync runs and its external ids) and `/data/integrations/:connectionId/sync-runs/:syncRunId` (one sync run). API clients and webhook endpoints are under Settings › Developer.

- Imports: upload the file with `POST /api/v1/files` (purpose `IMPORT_SOURCE`) and create the import with `POST /api/v1/imports`; it moves through `UPLOADED`, `VALIDATING`, `VALIDATED` (or `INVALID`), `DIFFING`, `DIFF_READY`, `SUBMITTED`, `APPROVED`, `COMMITTING` and `COMMITTED`, or `FAILED`, `REJECTED`, `CANCELLED`. `GET …/rows`, `GET …/diff` (the dry-run diff: what the commit would change) and `GET …/error-report`; `POST …/submit` asks for approval of the commit (subject `IMPORT_COMMIT`; `import.approve` by someone other than the uploader); `POST …/cancel`. An import of a legacy template whose commit itself approves something — the SKU SSP book version, the activation of the contracts with their judgement records and estimates, a contract modification — is approved by people who could approve that thing directly: its approver also holds that permission (`ssp.approve`, `contract.approve` with `judgement.review` and `estimate.approve`, `modification.approve`), and where the underlying approval takes a second approver — an SSP value that moves by more than its threshold, an activation of USD 1,000,000.00 or more — the import waits for that second person too. A workspace in which nobody holds both `import.approve` and the underlying permission cannot approve such an import: create and approve the item directly instead.
- Templates: `GET /api/v1/import-templates` and `GET /api/v1/import-templates/{code}/download`. The four legacy v1 templates are `legacy_sku_ssp`, `legacy_contract_setup`, `legacy_progress_tracking` and `legacy_contract_modification` (exact header set, order ignored, first sheet). Mapping profiles for other file shapes live under `/api/v1/import-mapping-profiles`.
- Exceptions: an item is `OPEN`, `IN_PROGRESS`, `RESOLVED`, `WAIVED` or `DISMISSED`; `POST /api/v1/exceptions/{item_id}/assign`, `reprocess`, `resolve`, `dismiss` or `request-waiver` (`exception.resolve`, `exception.waive`). Source records behind an item: `GET /api/v1/source-records/{source_record_id}`.

## Approvals

Routes `/approvals` (waiting for me), `/approvals/submitted` (submitted by me), `/approvals/all`, `/approvals/requests/:requestId` and `/approvals/delegations`. The tab "Waiting for me" shows the number of pending requests you can decide (`GET /api/v1/approvals?assigned_to_me=true&status=PENDING&count=true`, header `X-Erev-Total-Count`); the rail shows no count at this revision.

Every request names its subject: `SSP_BOOK_VERSION`, `SSP_OVERRIDE`, `CONTRACT_ACTIVATION`, `MODIFICATION`, `MANUAL_EVENT`, `ESTIMATE_VERSION`, `MANUAL_ADJUSTMENT`, `REGISTRY_VERSION`, `RULE_SET_VERSION`, `POB_TEMPLATE_VERSION`, `ACCOUNT_MAPPING_VERSION`, `FX_RATE_SET_VERSION`, `ROLE_CHANGE`, `ROLE_ASSIGNMENT`, `SOD_EXCEPTION`, `PERIOD_LOCK`, `PERIOD_REOPEN`, `IMPORT_COMMIT`, `CONTRACT_VOID` or `COMBINATION_GROUP`. Decide with `POST /api/v1/approvals/{approval_request_id}/approve` or `reject` (a comment is required to reject), withdraw your own request with `withdraw`, and approve several at once with `POST /api/v1/approvals/bulk-approve`. The approver is never the submitter; a request whose subject changed after submission is voided as stale; some subjects need a fresh authenticator code. You see and decide requests within the legal entities your roles cover: a request names the entities of its subject, and deciding it needs the step's permission — and the step's role, when it names one — for every one of them; a request outside your entities answers 404 like an unknown id, and the request shows its entities (`entities`, `entity_count`, `all_entities`). A subject whose entities changed after submission is voided as stale at the decision. Delegations (`/api/v1/approval-delegations`, revoke) hand your decisions to a colleague for a period — the permission, not the view: the colleague decides only requests whose entities their own roles cover. The tab "Delegations" (`/approvals/delegations`), shown to a holder of an approval permission, lists the delegations you gave and received, creates one and revokes one. Choosing the delegate on the screen needs the member directory (`user.manage`), which among the default roles only the Tenant Admin holds; another approver's delegation is created through the API with the delegate's membership id.

A pending request marked **Needs an independent approver** has nobody eligible to decide its
active step. Ask an access administrator to review the required role, entity coverage and
separation of duties. The warning is recalculated when the queue or request is read, so it clears
when an eligible person gains access. When a request or its next step starts without an eligible
approver, access administrators covering the request receive an alert containing its reference.
Notification preferences apply; sandbox workspaces send no email.

## Settings

Route `/settings` is the section index. Your preferences: `/settings/notifications`, `/settings/profile` (password, authenticator enrolment and recovery codes: `POST /api/v1/me/password`, `POST /api/v1/me/mfa/enroll`, `POST /api/v1/me/mfa/confirm`, `POST /api/v1/me/recovery-codes`). Workspace: `/settings/setup`, `/settings/workspace` (`PATCH /api/v1/tenant` with `display_name` and `default_locale`, `settings.manage` for all entities), `/settings/entities` (entities and their books), `/settings/calendars` (fiscal calendars; `POST /api/v1/calendars/{calendar_id}/generate-year`), `/settings/currencies` (tenant currencies and FX rate sets with versions and approval), `/settings/chart-of-accounts` (`/api/v1/gl-accounts`, `/api/v1/dimensions`). Reference data: `/settings/customers`, `/settings/related-party-groups`, `/settings/products` (bundle components and the principal-agent change proposal). Access: `/settings/users`, `/settings/roles`, `/settings/separation-of-duties`, `/settings/access-reviews`, `/settings/security`, `/settings/support-access`. Developer: `/settings/developer` (API clients with secret rotation and revocation, webhook endpoints and deliveries); a new API client is Pending approval until another person who holds `access.approve` for its entities approves the request, and its first secret is then issued with Rotate secret. On `/settings/workspace` a change is submitted as one policy version per changed category; where a draft or tested version of a category is already open the form names it with a link to its page and does not submit that category, and a draft that nobody wants is finished on that page by stating the values in force and submitting it, since no command deletes a draft.

Users are global identities with one membership per workspace. A workspace is shown a person's last sign-in and MFA state only while the person is its member: for an invited or a removed member the Users screen reads "Not shown" in both, and the name reads as the email address unless this workspace's invitation added the person to eRev. A person who is invited and has no active membership anywhere — removed and invited again, say — can still reset a forgotten password: the reset email is sent for the workspace of the open invitation. Invite with `POST /api/v1/users` (`user.manage`), then `resend-invitation`, `suspend`, `reactivate`, `remove` and `reset-mfa` on `/api/v1/users/{membership_id}`; role assignments need approval (`ROLE_ASSIGNMENT`), as do role changes and separation-of-duties exceptions; a role is revoked at once, with a reason, by a holder of `role.manage` other than the member (`POST /api/v1/role-assignments/{assignment_id}/revoke`). A person who was removed from the workspace is invited again with `POST /api/v1/users`: the membership is the one the person had, its earlier roles stay revoked, and the roles of the new invitation are requested with it. Removing a member also ends every approval delegation given to that member; it does not come back with a new invitation. A person's personal data is erased with `POST /api/v1/users/{membership_id}/anonymise` after a fresh authenticator code, by an administrator other than the person; the procedure, including the second run that completes the erasure in the person's other workspaces, is runbook RB-14. Access review campaigns (`/api/v1/access-reviews`) and time-boxed support grants (`/api/v1/support-grants`, approved by `support_grant.approve` for all entities) are audited like every command.

## Sandboxes and scenarios

A sandbox is a workspace of kind `SANDBOX`: it runs the same engine, it can never export journals through an adapter (the command answers 403 `sandbox-restricted`), it cannot be converted to production and it cannot write to a production workspace. A production workspace is never overwritten, rolled back or dropped by any user or API operation.

- Copy production into a sandbox: `POST /api/v1/tenant/snapshots` with `known_at` (the instant the copy is taken as of), `purpose` `SANDBOX_COPY` and the sandbox `name`; the `TENANT_SNAPSHOT` job answers 202 with `Location` and the `X-Erev-Tenant-Snapshot-Id` header, and `GET /api/v1/tenant/snapshots/{tenant_snapshot_id}` shows the status, the row counts, the target sandbox and the manifest (`…/manifest`). The command needs `tenant.snapshot` for all entities and a fresh authenticator code, and it is audited in both workspaces.
- A person who was invited and had not accepted when the copy was taken is not a member of the copy: the invitation is shown there as removed, and an administrator of the copy can invite the person again.
- Keep a stored backup: the same command with purpose `STORED_BACKUP` stores the snapshot without creating a sandbox; `GET /api/v1/tenant/snapshots` lists them. Purpose `SANDBOX_SEED`, like `SANDBOX_COPY`, asks the sandbox `name` and loads that sandbox in the same job.
- Restore: `POST /api/v1/tenant/sandboxes` with a `SUCCEEDED` `tenant_snapshot_id` and a `name` creates a new sandbox from the stored snapshot. A restore never targets production.
- Reset a sandbox: `POST /api/v1/tenant/reset` (`sandbox.reset`, with a fresh authenticator code) replaces the sandbox by a successor, from its seed snapshot (`mode` `SNAPSHOT`) or empty (`EMPTY`); the old one is archived and nothing is deleted. It answers 202 with the `SANDBOX_RESET` job. A production workspace answers 409 `production-reset-forbidden`.
- Scenario workspaces for forecasts and deal previews (`scenario.use`) are sandboxes created from a production snapshot; the scenario and forecast commands are not in the API at this revision.

The Sandbox copies settings page is `/settings/sandbox`. In a production workspace it creates a sandbox copy and lists the sandboxes copied from the workspace and the stored snapshots, each with its restore into a new sandbox; in a sandbox it says what the workspace was copied from and offers the reset.

## AI assistance

AI is off by default in every workspace, and a second setting, also off by default, governs whether contract text may be sent to the provider. Every AI output is a proposal with citations, in status `proposed`, `accepted`, `rejected`, `expired` or `failed`; accepting a proposal runs the normal command as the accepting user with its approvals and separation of duties, and no AI code path writes accounting data. Status at this revision: the OpenAPI document has no AI route, `PATCH /api/v1/tenant` accepts only `display_name` and `default_locale`, and the only provider in the code base is the deterministic fake used by the test suites; the Anthropic adapter and the proposal commands are not built. Explain (see Contracts) is a deterministic recomputation, not AI.

## Coming from eRev desktop

eRev Cloud rebuilds the desktop application eRev (the Excel templates over `ASC606.db`). The map below is the same one Home links to on a workspace using the legacy-parity preset. Legacy names such as POB, Stratification or Unbilled A/R appear only here and in the legacy export column definitions.

### The 14 desktop buttons

| Id | Desktop group and button | What it did | eRev Cloud feature | Where now | What changes for you |
|---|---|---|---|---|---|
| LTM-01 | Contract Operations › Load SSPs | Replaced the whole `SKU_SSP` table on every upload | "Legacy v1: SKU SSP" import creating an SSP book version submitted for approval; versions append | `/data/imports/new` (template `legacy_sku_ssp`); `/policies/ssp-books` | SSPs need an approver before use; history is kept; no silent replacement |
| LTM-02 | Contract Operations › Load Contracts | Appended setup rows and allocated immediately | "Legacy v1: Contract Setup" import with a dry-run allocation walk; approval activates | `/data/imports/new` (template `legacy_contract_setup`); `/contracts` | Allocation is visible before commit; re-uploading an existing contract is refused |
| LTM-03 | Contract Operations › Load Delivery and Billing | Applied deliveries and billings at a typed date; dropped blank-memo rows | "Legacy v1: Contract Progress Tracking" import with an effective date, modern CSV, or integrations | `/data/imports/new` (template `legacy_progress_tracking`) | Duplicate rows are summed with a notice; blank memos warn instead of dropping rows; over-delivery names the obligation; late dates post to the first open period |
| LTM-04 | Mod Operations › Prospective Contract Mod | Pooled reallocation over remaining SSP | "Legacy v1: Contract Modification" with mode `prospective`, or the modification wizard | `/data/imports/new` (template `legacy_contract_modification`); `/contracts/:contractId/modifications/new` | The system proposes the treatment and shows an impact preview; approval required |
| LTM-05 | Mod Operations › Retrospective Contract Mod | Full retrospective re-allocation with catch-ups | Mode `retrospective`, or the cumulative catch-up treatment | as LTM-04 | Same as LTM-04 |
| LTM-06 | Mod Operations › POB Specific VC | Added a price change to one obligation with a catch-up | Mode `pob_price_change`, or a price change event on the obligation | as LTM-04; `POST /api/v1/contracts/{contract_id}/events` | Quantity must be 0; variable consideration elements cannot be targeted |
| LTM-07 | Journals and Reporting › Revenue Journal Entries | Excel gross and delta JE reports for a date range, sometimes 0.01 out of balance | Journal runs per entity, book and period with approval, export and acknowledgement; gross and adjustment date-range views | `/journals`; `/journals/entries` | Every batch balances; exports go to CSV, NetSuite or QuickBooks Online adapters |
| LTM-08 | Journals and Reporting › Contract History | Excel of all versions in a date range | "Contract history" report and the 71-column legacy export (`contract_history`, `legacy_contract_history_export`) | `/reports/:reportCode` | Parameterized; a start date after the end date is refused |
| LTM-09 | Journals and Reporting › Latest Contract Status | Excel of the latest version per POB | "Latest contract status" report and its legacy export (`latest_contract_status`, `legacy_latest_contract_export`) | `/reports/:reportCode` | Run record with a hash for each export |
| LTM-10 | Premium Database Functions › Backup Database | Copied the database file to one backup slot | Create a sandbox copy or a stored backup | `/settings/sandbox`; `POST /api/v1/tenant/snapshots` | The copy is a sandbox workspace you can open; production is untouched |
| LTM-11 | Premium Database Functions › Restore from Backup | Deleted the live database and copied the backup over it | Restore into a new sandbox from a stored snapshot; corrections in production use void, reversal or reopen | `/settings/sandbox`; `POST /api/v1/tenant/sandboxes` | Production data is never overwritten |
| LTM-12 | Premium Database Functions › !Reset Database Completely! | Dropped every table | Reset sandbox (sandbox workspaces only; refused for production) | `/settings/sandbox` | Refused for production |
| LTM-13 | Premium Database Functions › Append from Another | Positional insert of another database's rows without de-duplication | Legacy database import (opening balances) or template replay, each with reconciliation and approval | `/data/migrations/:migrationId`; the migration guide | Duplicates are refused; differences are reconciled before promotion |
| LTM-14 | Premium Database Functions › Purge Contracts | Deleted rows by name and date range | Void contract with approval; reversal lines in the first open period | `POST /api/v1/contracts/{contract_id}/request-void` | Nothing is deleted; history stays |

### The four templates

| Id | Desktop template | eRev Cloud import template | Header rule |
|---|---|---|---|
| LTM-T1 | SKU SSP Template (9 columns) | "Legacy v1: SKU SSP" (`legacy_sku_ssp`) | Exact header set; order ignored; first sheet |
| LTM-T2 | Contract Setup Template (16 columns) | "Legacy v1: Contract Setup" (`legacy_contract_setup`) | as above |
| LTM-T3 | Contract Progress Tracking Template (9 columns) | "Legacy v1: Contract Progress Tracking" (`legacy_progress_tracking`) with an effective date | as above |
| LTM-T4 | Contract Modification Template (15 columns) | "Legacy v1: Contract Modification" (`legacy_contract_modification`) with mode `prospective`, `retrospective` or `pob_price_change` and an effective date | as above |

### Retired behaviours

| Desktop behaviour | eRev Cloud |
|---|---|
| Licence key dialog and premium gating | Removed; every feature is standard |
| End-of-life shutdown on 2025-12-31 | Removed |
| External links and background images in the window | Removed; no outbound requests from the browser application |
| Success and error popups | Toasts for outcomes, findings in the dry-run diff, exception items and notifications |
| Typed "Current Period" date prompt | Effective date in the import wizard; the context pill for reads |
| Excel files overwritten in the application folder | Downloads with report run records and hashes |
| `Processing Time Log` naive local timestamp | `recorded_at` in UTC and the audit log |
| Forecasting by copying the application folder and re-running templates | Scenario workspaces (specified; not in the API at this revision) |
| Direct SQLite access for BI tools | CSV extracts with manifests, including the 71-column dataset |

## Demo workspaces

`make seed` provisions the demo workspaces through the same commands a customer would use (`erev seed demo`): each tenant is created, its persona users are invited with their PRD roles for all entities, invitations are accepted, the personas holding an MFA-requiring permission are enrolled, as is Maya Chen, who prepares the reconciliations of the close and needs a verified second factor to sign them, custom roles are added, and the tenant's registered content builders run. It writes the credentials it generated to `.run/demo-credentials.txt`; the demo password is read from `EREV_DEMO_PASSWORD` and the authenticator seed from `EREV_DEMO_TOTP_SECRET` (both documented in `.env.example`; never printed). `demo.erev` is not a routable domain: notifications go to the fake mail adapter. Demo company names are fictitious and carry the suffix "(Demo)". A tenant already seeded by the same generator version is skipped; a tenant whose `is_demo` is false is refused.

Content at this revision (Codex production-20260922-0017 P8-DEP7-DEMO-1): Avenmoor Holdings carries the background contracts and import history its builders create; the six industry tenants carry their entity structure, chart of accounts, account mapping and draft industry templates; the Legacy parity pack is provisioned with its personas only — no content builder exists for it yet, so the replayed legacy UAT files and the golden values it is specified to show (REQ-DEMO-002) are pending. The journey content of PRD §2 is built incrementally by the DMO items.

| Code | Display name | Provisioned today | Specified purpose |
|---|---|---|---|
| `legacy-parity` | Legacy parity pack (Demo) | tenant and personas; content pending | The legacy UAT files replayed under the legacy-parity preset; golden values visible |
| `avenmoor` | Avenmoor Holdings (Demo) | tenant, personas, background contracts and imports | Multi-industry journey workspace (mid-market and enterprise features) |
| `fernhill` | Fernhill Software, Inc. (Demo) | tenant, personas, reference structure | Software and cloud; the guided tour |
| `bracken` | Bracken Robotics Corp. (Demo) | tenant, personas, reference structure | Devices and industrial products |
| `granitefield` | Granitefield Engineering Group (Demo) | tenant, personas, reference structure | Engineering, construction and government |
| `juniper-street` | Juniper Street Coffee Co. (Demo) | tenant, personas, reference structure | Consumer brands and franchising |
| `riverbend` | Riverbend Health System (Demo) | tenant, personas, reference structure | Healthcare providers |
| `wayfarer` | Wayfarer Marketplace (Demo) | tenant, personas, reference structure | Platforms and travel |

The demo users are one named persona per default role, `<name>@demo.erev`: Maya Chen (Revenue Accountant, SSP Analyst), Priya Raman (Revenue Reviewer, SSP Approver), Marcus Webb and Elena Sokolova (Controllers; Marcus also SSP Approver), Robert Adeyemi (Viewer), Hannah Lindqvist and Samuel Ortiz (Auditors), Tomás Rivera and Grace Okafor (Tenant Admins), Nikhil Rao (Integration Admin) and Jordan Blake (Viewer and a custom deal desk role). A user may hold several roles; every assignment covers all entities.

**The month of the demo workspaces.** Avenmoor Holdings is seeded as of September 2026: its periods January to September 2026 are open and October 2026 onwards are still to come (state "Future"). `make seed CLOSE=1` (`erev seed demo --with-close`) also closes January to August 2026 for Avenmoor Inc. (`AVM-US`) in its primary book, `ASC606`, month by month as the personas would: Maya Chen runs the close, exports the journal as a CSV file, records the document reference of the ledger and reconciles, Priya Raman approves the journal and reviews the reconciliations, and Marcus Webb locks the month. A lock took two and a half to three minutes when it was measured, which is why a seed closes only when it is asked. The trial balance of a seeded month is written from the subledger, so its reconciliation shows how the tie-out reads, not two independent books. The other entities and the `IFRS15` book stay open, and the reopening of June of the specified history is pending. A workspace that was seeded without its close is not closed by a later seed, because its open items hold every lock: the command says so and names `make seed RESET=1 CLOSE=1`. The scheduler that opens a period on its start date leaves the demo workspaces alone, so they keep this month whatever the day they are used. A later period opens when someone opens it by hand (`POST /periods/{id}/open`) or when the period before it is locked.

- **Dating a contract today (known limitation).** "Today" on a screen is the date of the wall clock. A contract or an event dated today in a demo workspace therefore lies in a period that is still to come, and a contract in GBP, EUR or JPY finds no exchange rate for that date: the seeded rates end on 30 September 2026. Date it within September 2026, or open the later period and load its rates first (Settings, "Currencies and rates").
