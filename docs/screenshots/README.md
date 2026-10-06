# eRev Cloud: screenshots of the system

The screens of eRev Cloud as the release candidate of 1.0 draws them. Nothing here is a mock-up: each image was
written by the product's own end-to-end harness while it drove the built application in a browser.

- **`screens/`**: 126 named captures, each in the light and the dark theme (252 files). 108 are
  the captures of the e2e project `screens` and of the smoke journey (`frontend/e2e/projects/screens.spec.ts`,
  `frontend/e2e/journeys/rc-smoke.journey.ts`; the helper is `frontend/e2e/support/screens.ts`). Captured on
  2026-10-04 at commit `b8f4b9e2`, whose code is the release candidate's (`f8e46e542`): 1440 by 900 pixels,
  English, UTC, on the seeded demo workspaces. A value that changes from run to run, such as the time of the last
  computation, is covered by the harness with a magenta block.
  The other 18 are screens of Settings and of sign-in that the `screens` project does not capture. They were
  captured on the same day, with the same helper and on the same seeded world, by a supplementary spec that is
  not part of the release candidate's e2e projects; its text is kept here as
  [`extra-screens.spec.ts.txt`](extra-screens.spec.ts.txt), and it opens each screen as a demo persona, asserts
  nothing and changes no data.
- **`qa-pass/`**: 45 captures of the multi-role browser QA pass of record on the release candidate
  (`docs/qa/RC-multi-role-qa-2026-10-03-f8e46e54.md`): twelve members, a contract from draft to active, and one
  month closed and locked, on the demo workspace whose earlier months are closed.
- **[GALLERY.md](GALLERY.md)** shows every light capture in one page, by screen family.
- **[The illustrated guide](../guides/illustrated-guide.md)** explains each screen and task with these captures.
- `index.json` lists the captures for tools.

The companies and people in the captures are the fictitious demo workspaces ("(Demo)") and their personas
(`docs/guides/user-guide.md`, "Demo workspaces"). Some captures show a small workspace that a test builds for one
screen, for example "Setup capture (Demo)". The screen ids (SF-01 to SF-24) and routes (RT-nn) are those of the
screen specification, `docs/design/SCREENS.md` and `docs/design/SCREENS_B.md`.

Routed screens without a capture: the pages a person reaches only through a link in an email or a forced step
of sign-in ("Accept invitation", "Set up multi-factor authentication", the second step of a password reset), the
page of a legacy migration (the demo workspaces hold none) and the page of an access review campaign (the
seeded workspace holds none).

To make the captures again: `EREV_GATE_KEEP_CONTEXT=1 make e2e PROJECT=avenmoor-serial,screens`, then copy
`frontend/e2e/.screens/` out of the kept gate context under `.run/gates/` (the harness removes a context that is
not kept).

## Captures by screen

### SF-22: Sign in

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-22` | SF-22 Sign in (RT-01 /sign-in), persona unauthenticated | [light](screens/sf-22.light.png) | [dark](screens/sf-22.dark.png) |
| `sf-22-mfa-challenge` | SF-22:mfa-challenge Verify your sign-in (RT-02 /sign-in/mfa), persona marcus | [light](screens/sf-22-mfa-challenge.light.png) | [dark](screens/sf-22-mfa-challenge.dark.png) |
| `sf-22-session-expired` | SF-22 Sign in (RT-01 /sign-in), persona unauthenticated | [light](screens/sf-22-session-expired.light.png) | [dark](screens/sf-22-session-expired.dark.png) |
| `sf-22-password-reset` | SF-22:password-reset Reset password (/password/reset), persona unauthenticated | [light](screens/sf-22-password-reset.light.png) | [dark](screens/sf-22-password-reset.dark.png) |
| `sf-22-password-change` | SF-22:password-change Change password (/password/change), persona maya | [light](screens/sf-22-password-change.light.png) | [dark](screens/sf-22-password-change.dark.png) |

### SF-23: Workspace, top bar and context pill

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-23-select` | SF-23:select Choose a workspace (RT-06 /select-workspace), persona robert | [light](screens/sf-23-select.light.png) | [dark](screens/sf-23-select.dark.png) |
| `sf-23` | SF-23 Context pill (placement, /settings/workspace), persona tomas | [light](screens/sf-23.light.png) | [dark](screens/sf-23.dark.png) |

### SF-01: Home

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-01-viewer` | SF-01 Home (RT-07 /home), personas priya, robert and maya | [light](screens/sf-01-viewer.light.png) | [dark](screens/sf-01-viewer.dark.png) |
| `sf-01-approver` | SF-01 Home (RT-07 /home), personas priya, robert and maya | [light](screens/sf-01-approver.light.png) | [dark](screens/sf-01-approver.dark.png) |

### SF-24: Command palette and search

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-24-results` | SF-24 Command palette and SF-24:results Search results (RT-95 /search), persona maya | [light](screens/sf-24-results.light.png) | [dark](screens/sf-24-results.dark.png) |
| `sf-24-palette` | SF-24 Command palette and SF-24:results Search results (RT-95 /search), persona maya | [light](screens/sf-24-palette.light.png) | [dark](screens/sf-24-palette.dark.png) |

### SF-21: Notifications

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-21` | SF-21 Notifications (placement, /approvals), persona grace | [light](screens/sf-21.light.png) | [dark](screens/sf-21.dark.png) |

### SF-02: Contracts list

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-02` | SF-02 Contracts (RT-08 /contracts), persona maya | [light](screens/sf-02.light.png) | [dark](screens/sf-02.dark.png) |
| `sf-02-compact` | SF-03 Contract workbench (RT-10 /contracts/:contractId/obligations), persona maya | [light](screens/sf-02-compact.light.png) | [dark](screens/sf-02-compact.dark.png) |

### SF-03: Contract workbench

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `rc-smoke-06-schedules` | The release candidate's smoke journey, step RC-SMOKE.6 (SF-03:schedules) | [light](screens/rc-smoke-06-schedules.light.png) | [dark](screens/rc-smoke-06-schedules.dark.png) |
| `sf-03` | SF-03 Contract workbench (RT-10 /contracts/:contractId/obligations), persona maya | [light](screens/sf-03.light.png) | [dark](screens/sf-03.dark.png) |
| `sf-03-obligation` | SF-03:obligation Obligation detail pane (RT-11 /contracts/:contractId/obligations/:obligationId), persona maya | [light](screens/sf-03-obligation.light.png) | [dark](screens/sf-03-obligation.dark.png) |
| `sf-03-compact` | SF-03 Contract workbench (RT-10 /contracts/:contractId/obligations), persona maya | [light](screens/sf-03-compact.light.png) | [dark](screens/sf-03-compact.dark.png) |
| `sf-03-schedules` | SF-03:schedules Schedules tab (RT-14 /contracts/:contractId/schedules), persona maya | [light](screens/sf-03-schedules.light.png) | [dark](screens/sf-03-schedules.dark.png) |
| `sf-03-billing` | SF-03:billing Billing tab (RT-15 /contracts/:contractId/billing), persona maya | [light](screens/sf-03-billing.light.png) | [dark](screens/sf-03-billing.dark.png) |
| `sf-03-journals` | SF-03:journals Journals tab (RT-16 /contracts/:contractId/journals), persona maya | [light](screens/sf-03-journals.light.png) | [dark](screens/sf-03-journals.dark.png) |
| `sf-03-modifications` | SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya | [light](screens/sf-03-modifications.light.png) | [dark](screens/sf-03-modifications.dark.png) |
| `sf-03-estimate-version` | SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya | [light](screens/sf-03-estimate-version.light.png) | [dark](screens/sf-03-estimate-version.dark.png) |
| `sf-03-estimates` | SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya | [light](screens/sf-03-estimates.light.png) | [dark](screens/sf-03-estimates.dark.png) |
| `sf-03-estimate` | SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya | [light](screens/sf-03-estimate.light.png) | [dark](screens/sf-03-estimate.dark.png) |
| `sf-03-estimate-current` | SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya | [light](screens/sf-03-estimate-current.light.png) | [dark](screens/sf-03-estimate-current.dark.png) |
| `sf-03-history` | SF-03:history History tab (RT-18 /contracts/:contractId/history), persona maya | [light](screens/sf-03-history.light.png) | [dark](screens/sf-03-history.dark.png) |
| `sf-03-new` | SF-03:new and SF-03:edit Draft contract form (RT-09 /contracts/new, RT-19 /contracts/:contractId/edit), persona maya | [light](screens/sf-03-new.light.png) | [dark](screens/sf-03-new.dark.png) |
| `sf-03-new-lines` | SF-03:new and SF-03:edit Draft contract form (RT-09 /contracts/new, RT-19 /contracts/:contractId/edit), persona maya | [light](screens/sf-03-new-lines.light.png) | [dark](screens/sf-03-new-lines.dark.png) |
| `sf-03-edit` | SF-03:new and SF-03:edit Draft contract form (RT-09 /contracts/new, RT-19 /contracts/:contractId/edit), persona maya | [light](screens/sf-03-edit.light.png) | [dark](screens/sf-03-edit.dark.png) |
| `sf-03-estimate-discard` | SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya | [light](screens/sf-03-estimate-discard.light.png) | [dark](screens/sf-03-estimate-discard.dark.png) |

### SF-07: Modifications

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-07` | SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya | [light](screens/sf-07.light.png) | [dark](screens/sf-07.dark.png) |
| `sf-07-detail` | SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya | [light](screens/sf-07-detail.light.png) | [dark](screens/sf-07-detail.dark.png) |
| `sf-07-detail-approval` | SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya | [light](screens/sf-07-detail-approval.light.png) | [dark](screens/sf-07-detail-approval.dark.png) |
| `sf-07-change` | SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya | [light](screens/sf-07-change.light.png) | [dark](screens/sf-07-change.dark.png) |

### Explain panel

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `explain-panel` | Explain panel (placement on SF-03, URL parameter explain), persona maya | [light](screens/explain-panel.light.png) | [dark](screens/explain-panel.dark.png) |

### Calculation trace

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `x-trace` | X:trace Calculation trace (RT-96 /trace/:calcTraceId), persona maya | [light](screens/x-trace.light.png) | [dark](screens/x-trace.dark.png) |

### SF-04: Schedules

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-04-quarter` | SF-04 Schedules (RT-25 /schedules), persona marcus | [light](screens/sf-04-quarter.light.png) | [dark](screens/sf-04-quarter.dark.png) |
| `sf-04-avm-us-quarter` | SF-04 Schedules (RT-25 /schedules), persona marcus | [light](screens/sf-04-avm-us-quarter.light.png) | [dark](screens/sf-04-avm-us-quarter.dark.png) |

### SF-05: Close

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-05-open` | SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya | [light](screens/sf-05-open.light.png) | [dark](screens/sf-05-open.dark.png) |
| `sf-05-submit-lock-order` | SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya | [light](screens/sf-05-submit-lock-order.light.png) | [dark](screens/sf-05-submit-lock-order.dark.png) |
| `sf-05-submit-lock-refused` | SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya | [light](screens/sf-05-submit-lock-refused.light.png) | [dark](screens/sf-05-submit-lock-refused.dark.png) |
| `sf-05-journal-preview` | SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya | [light](screens/sf-05-journal-preview.light.png) | [dark](screens/sf-05-journal-preview.dark.png) |
| `sf-05-history` | SF-05:close-run, SF-05:history and SF-05:multi-entity (RT-99, RT-101, RT-27), personas maya and marcus | [light](screens/sf-05-history.light.png) | [dark](screens/sf-05-history.dark.png) |
| `sf-05-reconciliations-generated` | SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya | [light](screens/sf-05-reconciliations-generated.light.png) | [dark](screens/sf-05-reconciliations-generated.dark.png) |
| `sf-05-reconciliation-draft` | SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya | [light](screens/sf-05-reconciliation-draft.light.png) | [dark](screens/sf-05-reconciliation-draft.dark.png) |
| `sf-05-reconciliation-reviewer` | SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya | [light](screens/sf-05-reconciliation-reviewer.light.png) | [dark](screens/sf-05-reconciliation-reviewer.dark.png) |
| `sf-05-close-run` | SF-05:close-run, SF-05:history and SF-05:multi-entity (RT-99, RT-101, RT-27), personas maya and marcus | [light](screens/sf-05-close-run.light.png) | [dark](screens/sf-05-close-run.dark.png) |
| `sf-05-multi-entity` | SF-05:close-run, SF-05:history and SF-05:multi-entity (RT-99, RT-101, RT-27), personas maya and marcus | [light](screens/sf-05-multi-entity.light.png) | [dark](screens/sf-05-multi-entity.dark.png) |
| `sf-05-reconciliation-attach` | SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya | [light](screens/sf-05-reconciliation-attach.light.png) | [dark](screens/sf-05-reconciliation-attach.dark.png) |
| `sf-05-reconciliation-gl` | SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya | [light](screens/sf-05-reconciliation-gl.light.png) | [dark](screens/sf-05-reconciliation-gl.dark.png) |

### SF-06: Journals

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `rc-smoke-07-journal-run` | The release candidate's smoke journey, step RC-SMOKE.7 (SF-06:run) | [light](screens/rc-smoke-07-journal-run.light.png) | [dark](screens/rc-smoke-07-journal-run.dark.png) |
| `rc-smoke-09-run-batches` | The release candidate's smoke journey, step RC-SMOKE.9 (SF-06:run-batches) | [light](screens/rc-smoke-09-run-batches.light.png) | [dark](screens/rc-smoke-09-run-batches.dark.png) |
| `sf-06` | SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya | [light](screens/sf-06.light.png) | [dark](screens/sf-06.dark.png) |
| `sf-06-run` | SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya | [light](screens/sf-06-run.light.png) | [dark](screens/sf-06-run.dark.png) |
| `sf-06-run-lines` | SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya | [light](screens/sf-06-run-lines.light.png) | [dark](screens/sf-06-run-lines.dark.png) |
| `sf-06-run-batches` | SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya | [light](screens/sf-06-run-batches.light.png) | [dark](screens/sf-06-run-batches.dark.png) |
| `sf-06-entries` | SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya | [light](screens/sf-06-entries.light.png) | [dark](screens/sf-06-entries.dark.png) |

### SF-08: Reports

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `rc-smoke-10-waterfall` | The release candidate's smoke journey, step RC-SMOKE.10 (SF-08:report) | [light](screens/rc-smoke-10-waterfall.light.png) | [dark](screens/rc-smoke-10-waterfall.dark.png) |
| `rc-smoke-10-rpo` | The release candidate's smoke journey, step RC-SMOKE.10 (SF-08:report) | [light](screens/rc-smoke-10-rpo.light.png) | [dark](screens/rc-smoke-10-rpo.dark.png) |
| `sf-08` | SF-08 Reports (RT-31 /reports), persona robert | [light](screens/sf-08.light.png) | [dark](screens/sf-08.dark.png) |
| `sf-08-report-revenue-waterfall` | SF-08:report Report view (RT-32 /reports/:reportCode), persona marcus | [light](screens/sf-08-report-revenue-waterfall.light.png) | [dark](screens/sf-08-report-revenue-waterfall.dark.png) |
| `sf-08-dashboard-revenue` | SF-08:dashboard Revenue dashboard (RT-107 /reports/dashboards/:dashboardCode), persona robert | [light](screens/sf-08-dashboard-revenue.light.png) | [dark](screens/sf-08-dashboard-revenue.dark.png) |
| `sf-08-dashboard-revenue-default` | SF-08:dashboard Revenue dashboard (RT-107 /reports/dashboards/:dashboardCode), persona robert | [light](screens/sf-08-dashboard-revenue-default.light.png) | [dark](screens/sf-08-dashboard-revenue-default.dark.png) |
| `sf-08-report-legacy-contract-history-export` | SF-08:report Report view (RT-32 /reports/:reportCode), persona marcus | [light](screens/sf-08-report-legacy-contract-history-export.light.png) | [dark](screens/sf-08-report-legacy-contract-history-export.dark.png) |
| `sf-08-dashboard-revenue-entity` | SF-08:dashboard Revenue dashboard (RT-107 /reports/dashboards/:dashboardCode), persona robert | [light](screens/sf-08-dashboard-revenue-entity.light.png) | [dark](screens/sf-08-dashboard-revenue-entity.dark.png) |
| `sf-08-dashboard-revenue-categories` | SF-08:dashboard Revenue dashboard (RT-107 /reports/dashboards/:dashboardCode), persona robert | [light](screens/sf-08-dashboard-revenue-categories.light.png) | [dark](screens/sf-08-dashboard-revenue-categories.dark.png) |
| `sf-08-runs` | SF-08:runs Report runs (RT-106 /reports/runs, RT-33), persona marcus | [light](screens/sf-08-runs.light.png) | [dark](screens/sf-08-runs.dark.png) |
| `sf-08-run` | SF-08:runs Report runs (RT-106 /reports/runs, RT-33), persona marcus | [light](screens/sf-08-run.light.png) | [dark](screens/sf-08-run.dark.png) |

### SF-09: Audit log

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-09-audit-log` | SF-09:audit-log Audit log (RT-37 /reports/audit-log, RT-38), persona hannah | [light](screens/sf-09-audit-log.light.png) | [dark](screens/sf-09-audit-log.dark.png) |
| `sf-09-verification` | SF-09:audit-log Audit log (RT-37 /reports/audit-log, RT-38), persona hannah | [light](screens/sf-09-verification.light.png) | [dark](screens/sf-09-verification.dark.png) |

### SF-10: Imports

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `rc-smoke-02-import-review` | The release candidate's smoke journey, step RC-SMOKE.2 (SF-10:detail) | [light](screens/rc-smoke-02-import-review.light.png) | [dark](screens/rc-smoke-02-import-review.dark.png) |
| `sf-10` | SF-10 Imports (RT-42 /data/imports), persona maya | [light](screens/sf-10.light.png) | [dark](screens/sf-10.dark.png) |
| `sf-10-new` | SF-10:new New import (RT-43 /data/imports/new), persona maya | [light](screens/sf-10-new.light.png) | [dark](screens/sf-10-new.dark.png) |
| `sf-10-detail` | SF-10:detail Import (RT-44 /data/imports/:importId/:step), persona maya | [light](screens/sf-10-detail.light.png) | [dark](screens/sf-10-detail.dark.png) |
| `sf-10-templates` | SF-10:templates Import templates (RT-45 /data/templates), persona maya | [light](screens/sf-10-templates.light.png) | [dark](screens/sf-10-templates.dark.png) |

### SF-11: Exceptions

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-11` | SF-11 Exceptions (RT-46 /data/exceptions), persona maya | [light](screens/sf-11.light.png) | [dark](screens/sf-11.dark.png) |
| `sf-11-item` | SF-11:item Exception (RT-47 /data/exceptions/:exceptionId), persona maya | [light](screens/sf-11-item.light.png) | [dark](screens/sf-11-item.dark.png) |
| `sf-11-blocking` | SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya | [light](screens/sf-11-blocking.light.png) | [dark](screens/sf-11-blocking.dark.png) |

### SF-16: Integrations

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-16-add-connection` | SF-16 Integrations (RT-48 /data/integrations, RT-49, RT-50), persona nikhil | [light](screens/sf-16-add-connection.light.png) | [dark](screens/sf-16-add-connection.dark.png) |
| `sf-16` | SF-16 Integrations (RT-48 /data/integrations, RT-49, RT-50), persona nikhil | [light](screens/sf-16.light.png) | [dark](screens/sf-16.dark.png) |
| `sf-16-connection` | SF-16 Integrations (RT-48 /data/integrations, RT-49, RT-50), persona nikhil | [light](screens/sf-16-connection.light.png) | [dark](screens/sf-16-connection.dark.png) |
| `sf-16-sync-run` | SF-16 Integrations (RT-48 /data/integrations, RT-49, RT-50), persona nikhil | [light](screens/sf-16-sync-run.light.png) | [dark](screens/sf-16-sync-run.dark.png) |
| `sf-16-developer` | SF-16:developer API clients and webhooks (/settings/developer), persona tomas | [light](screens/sf-16-developer.light.png) | [dark](screens/sf-16-developer.dark.png) |

### SF-13: Policies

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-13-revenue` | SF-13:revenue Revenue policies (RT-59 /policies/revenue), persona maya | [light](screens/sf-13-revenue.light.png) | [dark](screens/sf-13-revenue.dark.png) |
| `sf-13-control-rules` | SF-13:control-rules Control rules (RT-60 /policies/control-rules), persona maya | [light](screens/sf-13-control-rules.light.png) | [dark](screens/sf-13-control-rules.dark.png) |
| `sf-13-rule-set-version` | SF-13:rule-set-version Rule set version (RT-62 /policies/rule-sets/:ruleSetId/versions/:versionId), persona maya | [light](screens/sf-13-rule-set-version.light.png) | [dark](screens/sf-13-rule-set-version.dark.png) |
| `sf-13-template-version` | SF-13:template-version Obligation template version (RT-61 /policies/templates/:templateId/versions/:versionId), persona maya | [light](screens/sf-13-template-version.light.png) | [dark](screens/sf-13-template-version.dark.png) |
| `sf-13-template-version-draft` | SF-13:template-version Obligation template version (RT-61 /policies/templates/:templateId/versions/:versionId), persona maya | [light](screens/sf-13-template-version-draft.light.png) | [dark](screens/sf-13-template-version-draft.dark.png) |
| `sf-13-accounting` | SF-13:accounting Accounting policies (RT-63 /policies/accounting, RT-64 /policies/accounting/:policyId), persona marcus | [light](screens/sf-13-accounting.light.png) | [dark](screens/sf-13-accounting.dark.png) |
| `sf-13-accounting-version` | SF-13:accounting Accounting policies (RT-63 /policies/accounting, RT-64 /policies/accounting/:policyId), persona marcus | [light](screens/sf-13-accounting-version.light.png) | [dark](screens/sf-13-accounting-version.dark.png) |
| `sf-13-account-mapping` | SF-13:account-mapping Account mapping (RT-69 /policies/account-mapping, RT-70 /policies/account-mapping/:mappingVersionId), persona marcus | [light](screens/sf-13-account-mapping.light.png) | [dark](screens/sf-13-account-mapping.dark.png) |
| `sf-13-account-mapping-version` | SF-13:account-mapping Account mapping (RT-69 /policies/account-mapping, RT-70 /policies/account-mapping/:mappingVersionId), persona marcus | [light](screens/sf-13-account-mapping-version.light.png) | [dark](screens/sf-13-account-mapping-version.dark.png) |
| `sf-13-ssp-books` | SF-13:ssp-books SSP books (RT-65 /policies/ssp-books), persona maya | [light](screens/sf-13-ssp-books.light.png) | [dark](screens/sf-13-ssp-books.dark.png) |
| `sf-13-ssp-book-version` | SF-13:ssp-book-version SSP book version (RT-66 /policies/ssp-books/:bookId/versions/:versionId), persona maya | [light](screens/sf-13-ssp-book-version.light.png) | [dark](screens/sf-13-ssp-book-version.dark.png) |
| `sf-13-ssp-calculator` | SF-13:ssp-calculator Historical SSP calculator (RT-67, RT-68), persona maya | [light](screens/sf-13-ssp-calculator.light.png) | [dark](screens/sf-13-ssp-calculator.dark.png) |
| `sf-13-ssp-calculator-run` | SF-13:ssp-calculator Historical SSP calculator (RT-67, RT-68), persona maya | [light](screens/sf-13-ssp-calculator-run.light.png) | [dark](screens/sf-13-ssp-calculator-run.dark.png) |

### SF-12: Approvals

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-12` | SF-12 Approvals (RT-54 /approvals), persona tomas | [light](screens/sf-12.light.png) | [dark](screens/sf-12.dark.png) |
| `sf-12-submitted-empty` | SF-12:submitted Submitted by me (RT-55 /approvals/submitted), personas maya and priya | [light](screens/sf-12-submitted-empty.light.png) | [dark](screens/sf-12-submitted-empty.dark.png) |
| `sf-12-submitted` | SF-12:submitted Submitted by me (RT-55 /approvals/submitted), personas maya and priya | [light](screens/sf-12-submitted.light.png) | [dark](screens/sf-12-submitted.dark.png) |
| `sf-12-all` | SF-12:all All requests (RT-56 /approvals/all), persona grace | [light](screens/sf-12-all.light.png) | [dark](screens/sf-12-all.dark.png) |
| `sf-12-request` | SF-12:request Request (RT-57 /approvals/requests/:requestId), persona grace | [light](screens/sf-12-request.light.png) | [dark](screens/sf-12-request.dark.png) |
| `sf-12-delegations` | SF-12:delegations Delegations (RT-58 /approvals/delegations), persona priya | [light](screens/sf-12-delegations.light.png) | [dark](screens/sf-12-delegations.dark.png) |
| `sf-12-bulk` | SF-21 Notifications (placement, /approvals), persona grace | [light](screens/sf-12-bulk.light.png) | [dark](screens/sf-12-bulk.dark.png) |

### SF-15: Settings

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-15` | SF-15 Settings (RT-71 /settings), persona tomas | [light](screens/sf-15.light.png) | [dark](screens/sf-15.dark.png) |
| `sf-15-notifications` | SF-15:notifications Notification preferences (RT-72 /settings/notifications), persona maya | [light](screens/sf-15-notifications.light.png) | [dark](screens/sf-15-notifications.dark.png) |
| `sf-15-profile` | SF-15:profile Profile (RT-73 /settings/profile), persona maya | [light](screens/sf-15-profile.light.png) | [dark](screens/sf-15-profile.dark.png) |
| `sf-15-chart-of-accounts` | SF-15:chart-of-accounts Chart of accounts (RT-78 /settings/chart-of-accounts), persona tomas | [light](screens/sf-15-chart-of-accounts.light.png) | [dark](screens/sf-15-chart-of-accounts.dark.png) |
| `sf-15-workspace` | SF-15:workspace Workspace settings (RT-110 /settings/workspace), persona tomas | [light](screens/sf-15-workspace.light.png) | [dark](screens/sf-15-workspace.dark.png) |
| `sf-15-sandbox` | SF-15:sandbox Sandbox copies (RT-84 /settings/sandbox), persona marcus | [light](screens/sf-15-sandbox.light.png) | [dark](screens/sf-15-sandbox.dark.png) |
| `sf-15-setup` | SF-15:setup Workspace setup (RT-74 /settings/setup), persona tomas | [light](screens/sf-15-setup.light.png) | [dark](screens/sf-15-setup.dark.png) |
| `sf-15-calendars` | SF-15:calendars Calendars (/settings/calendars), persona tomas | [light](screens/sf-15-calendars.light.png) | [dark](screens/sf-15-calendars.dark.png) |
| `sf-15-currencies` | SF-15:currencies Currencies and rates (/settings/currencies), persona tomas | [light](screens/sf-15-currencies.light.png) | [dark](screens/sf-15-currencies.dark.png) |
| `sf-15-customers` | SF-15:customers Customers (/settings/customers), persona tomas | [light](screens/sf-15-customers.light.png) | [dark](screens/sf-15-customers.dark.png) |
| `sf-15-related-party-groups` | SF-15:related-party-groups Related-party groups (/settings/related-party-groups), persona tomas | [light](screens/sf-15-related-party-groups.light.png) | [dark](screens/sf-15-related-party-groups.dark.png) |
| `sf-15-entities` | SF-15:entities Entities (/settings/entities), persona tomas | [light](screens/sf-15-entities.light.png) | [dark](screens/sf-15-entities.dark.png) |
| `sf-15-products` | SF-15:products Products (/settings/products), persona tomas | [light](screens/sf-15-products.light.png) | [dark](screens/sf-15-products.dark.png) |
| `sf-15-customer` | SF-15:customer Customer (/settings/customers/:customerId), persona tomas | [light](screens/sf-15-customer.light.png) | [dark](screens/sf-15-customer.dark.png) |
| `sf-15-product` | SF-15:product Product (/settings/products/:productId), persona tomas | [light](screens/sf-15-product.light.png) | [dark](screens/sf-15-product.dark.png) |

### SF-14: Access

| Capture | Screen, route and persona (as the test names them) | Light | Dark |
|---|---|---|---|
| `sf-14-users` | SF-14 Users (/settings/users), persona tomas | [light](screens/sf-14-users.light.png) | [dark](screens/sf-14-users.dark.png) |
| `sf-14-roles` | SF-14:roles Roles (/settings/roles), persona tomas | [light](screens/sf-14-roles.light.png) | [dark](screens/sf-14-roles.dark.png) |
| `sf-14-sod` | SF-14:sod Separation of duties (/settings/separation-of-duties), persona tomas | [light](screens/sf-14-sod.light.png) | [dark](screens/sf-14-sod.dark.png) |
| `sf-14-access-reviews` | SF-14:access-reviews Access reviews (/settings/access-reviews), persona tomas | [light](screens/sf-14-access-reviews.light.png) | [dark](screens/sf-14-access-reviews.dark.png) |
| `sf-14-security` | SF-14:security Security (/settings/security), persona tomas | [light](screens/sf-14-security.light.png) | [dark](screens/sf-14-security.dark.png) |
| `sf-14-support-access` | SF-14:support-access Support access (/settings/support-access), persona tomas | [light](screens/sf-14-support-access.light.png) | [dark](screens/sf-14-support-access.dark.png) |
| `sf-14-user` | SF-14:user Member (/settings/users/:membershipId), persona tomas | [light](screens/sf-14-user.light.png) | [dark](screens/sf-14-user.dark.png) |

## Captures of the QA pass

The file name carries the check's id in the QA record and the member who acted.

| File | Check | Image |
|---|---|---|
| `001-s-1-sign-in-landing-and-rail-maya.png` | S-1 sign in landing and rail (Maya) | [open](qa-pass/001-s-1-sign-in-landing-and-rail-maya.png) |
| `002-s-1-sign-in-landing-and-rail-priya.png` | S-1 sign in landing and rail (Priya) | [open](qa-pass/002-s-1-sign-in-landing-and-rail-priya.png) |
| `003-s-1-sign-in-landing-and-rail-marcus.png` | S-1 sign in landing and rail (Marcus) | [open](qa-pass/003-s-1-sign-in-landing-and-rail-marcus.png) |
| `004-s-1-sign-in-landing-and-rail-elena.png` | S-1 sign in landing and rail (Elena) | [open](qa-pass/004-s-1-sign-in-landing-and-rail-elena.png) |
| `005-s-1-sign-in-landing-and-rail-robert.png` | S-1 sign in landing and rail (Robert) | [open](qa-pass/005-s-1-sign-in-landing-and-rail-robert.png) |
| `006-s-1-sign-in-landing-and-rail-hannah.png` | S-1 sign in landing and rail (Hannah) | [open](qa-pass/006-s-1-sign-in-landing-and-rail-hannah.png) |
| `007-s-1-sign-in-landing-and-rail-samuel.png` | S-1 sign in landing and rail (Samuel) | [open](qa-pass/007-s-1-sign-in-landing-and-rail-samuel.png) |
| `008-s-1-sign-in-landing-and-rail-tomas.png` | S-1 sign in landing and rail (Tomas) | [open](qa-pass/008-s-1-sign-in-landing-and-rail-tomas.png) |
| `009-s-1-sign-in-landing-and-rail-grace.png` | S-1 sign in landing and rail (Grace) | [open](qa-pass/009-s-1-sign-in-landing-and-rail-grace.png) |
| `010-s-1-sign-in-landing-and-rail-nikhil.png` | S-1 sign in landing and rail (Nikhil) | [open](qa-pass/010-s-1-sign-in-landing-and-rail-nikhil.png) |
| `011-s-1-sign-in-landing-and-rail-jordan.png` | S-1 sign in landing and rail (Jordan) | [open](qa-pass/011-s-1-sign-in-landing-and-rail-jordan.png) |
| `012-g-1-invitation-for-one-entity-tomas.png` | G-1 invitation for one entity (Tomas) | [open](qa-pass/012-g-1-invitation-for-one-entity-tomas.png) |
| `013-g-2-the-second-administrator-decides-grace.png` | G-2 the second administrator decides (Grace) | [open](qa-pass/013-g-2-the-second-administrator-decides-grace.png) |
| `014-g-3-acceptance-lena.png` | G-3 acceptance (Lena) | [open](qa-pass/014-g-3-acceptance-lena.png) |
| `015-g-4-the-first-session-of-a-member-of-one-entity-lena.png` | G-4 the first session of a member of one entity (Lena) | [open](qa-pass/015-g-4-the-first-session-of-a-member-of-one-entity-lena.png) |
| `016-g-5-sign-out-and-a-sign-in-with-the-chosen-password-lena.png` | G-5 sign out and a sign in with the chosen password (Lena) | [open](qa-pass/016-g-5-sign-out-and-a-sign-in-with-the-chosen-password-lena.png) |
| `017-k-4-a-typed-address-report-run-of-avm-us-lena.png` | K-4 a typed address report run of avm us (Lena) | [open](qa-pass/017-k-4-a-typed-address-report-run-of-avm-us-lena.png) |
| `018-k-5-every-screen-she-can-open-lena.png` | K-5 every screen she can open (Lena) | [open](qa-pass/018-k-5-every-screen-she-can-open-lena.png) |
| `019-k-6-what-all-entities-offers-her-and-what-it-totals-lena.png` | K-6 what all entities offers her and what it totals (Lena) | [open](qa-pass/019-k-6-what-all-entities-offers-her-and-what-it-totals-lena.png) |
| `020-a-1-a-draft-on-sf-03-new-maya.png` | A-1 a draft on sf 03 new (Maya) | [open](qa-pass/020-a-1-a-draft-on-sf-03-new-maya.png) |
| `021-a-3-the-step-1-review-submitted-maya.png` | A-3 the step 1 review submitted (Maya) | [open](qa-pass/021-a-3-the-step-1-review-submitted-maya.png) |
| `022-a-4-the-step-1-review-reviewed-priya.png` | A-4 the step 1 review reviewed (Priya) | [open](qa-pass/022-a-4-the-step-1-review-reviewed-priya.png) |
| `023-a-5-the-assessment-maya.png` | A-5 the assessment (Maya) | [open](qa-pass/023-a-5-the-assessment-maya.png) |
| `024-a-6-submitted-for-activation-maya.png` | A-6 submitted for activation (Maya) | [open](qa-pass/024-a-6-submitted-for-activation-maya.png) |
| `025-a-7-the-activation-approved-priya.png` | A-7 the activation approved (Priya) | [open](qa-pass/025-a-7-the-activation-approved-priya.png) |
| `026-a-8-the-obligation-s-september-amount-every-place-maya.png` | A-8 the obligation s september amount every place (Maya) | [open](qa-pass/026-a-8-the-obligation-s-september-amount-every-place-maya.png) |
| `027-c-0-the-cockpit-before-the-close-marcus.png` | C-0 the cockpit before the close (Marcus) | [open](qa-pass/027-c-0-the-cockpit-before-the-close-marcus.png) |
| `028-c-1-the-pending-requests-of-the-month-priya.png` | C-1 the pending requests of the month (Priya) | [open](qa-pass/028-c-1-the-pending-requests-of-the-month-priya.png) |
| `029-c-2-the-exceptions-that-hold-the-period-maya.png` | C-2 the exceptions that hold the period (Maya) | [open](qa-pass/029-c-2-the-exceptions-that-hold-the-period-maya.png) |
| `030-c-3-the-hold-released-on-the-screen-maya.png` | C-3 the hold released on the screen (Maya) | [open](qa-pass/030-c-3-the-hold-released-on-the-screen-maya.png) |
| `031-c-5-the-soft-close-marcus.png` | C-5 the soft close (Marcus) | [open](qa-pass/031-c-5-the-soft-close-marcus.png) |
| `032-c-6-the-close-run-maya.png` | C-6 the close run (Maya) | [open](qa-pass/032-c-6-the-close-run-maya.png) |
| `033-c-7a-the-journal-run-jr-000009-submitted-maya.png` | C-7a the journal run jr 000009 submitted (Maya) | [open](qa-pass/033-c-7a-the-journal-run-jr-000009-submitted-maya.png) |
| `034-c-7b-the-journal-run-jr-000009-approved-priya.png` | C-7b the journal run jr 000009 approved (Priya) | [open](qa-pass/034-c-7b-the-journal-run-jr-000009-approved-priya.png) |
| `035-c-7d-the-ledger-s-reference-for-each-batch-of-jr-000009-maya.png` | C-7d the ledger s reference for each batch of jr 000009 (Maya) | [open](qa-pass/035-c-7d-the-ledger-s-reference-for-each-batch-of-jr-000009-maya.png) |
| `036-c-8a-billing-to-subledger-maya-priya.png` | C-8a billing to subledger (Maya, Priya) | [open](qa-pass/036-c-8a-billing-to-subledger-maya-priya.png) |
| `037-c-8b-subledger-to-gl-maya-priya.png` | C-8b subledger to gl (Maya, Priya) | [open](qa-pass/037-c-8b-subledger-to-gl-maya-priya.png) |
| `038-c-9-submitted-for-lock-the-screens-alone-maya.png` | C-9 submitted for lock the screens alone (Maya) | [open](qa-pass/038-c-9-submitted-for-lock-the-screens-alone-maya.png) |
| `039-c-10-the-lock-on-the-cockpit-marcus.png` | C-10 the lock on the cockpit (Marcus) | [open](qa-pass/039-c-10-the-lock-on-the-cockpit-marcus.png) |
| `040-c-12-the-locked-month-every-place-marcus.png` | C-12 the locked month every place (Marcus) | [open](qa-pass/040-c-12-the-locked-month-every-place-marcus.png) |
| `041-p-1-a-lock-request-on-its-own-screen-marcus-elena.png` | P-1 a lock request on its own screen (Marcus, Elena) | [open](qa-pass/041-p-1-a-lock-request-on-its-own-screen-marcus-elena.png) |
| `042-m-2-one-screen-per-area-she-holds-no-permission-for-tomas.png` | M-2 one screen per area she holds no permission for (Tomas) | [open](qa-pass/042-m-2-one-screen-per-area-she-holds-no-permission-for-tomas.png) |
| `043-m-2-one-screen-per-area-she-holds-no-permission-for-grace.png` | M-2 one screen per area she holds no permission for (Grace) | [open](qa-pass/043-m-2-one-screen-per-area-she-holds-no-permission-for-grace.png) |
| `044-e-4-the-waterfall-of-a-closed-month-on-screen-marcus.png` | E-4 the waterfall of a closed month on screen (Marcus) | [open](qa-pass/044-e-4-the-waterfall-of-a-closed-month-on-screen-marcus.png) |
| `045-e-5-home-s-key-figures-of-a-closed-month-on-screen-marcus.png` | E-5 home s key figures of a closed month on screen (Marcus) | [open](qa-pass/045-e-5-home-s-key-figures-of-a-closed-month-on-screen-marcus.png) |
