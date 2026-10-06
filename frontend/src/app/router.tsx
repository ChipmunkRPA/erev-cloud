// Route table (docs/dev-guide.md DG-FE-02; SCREENS §0.4, SCR-IA-06; PHASES BS-D-08, BS1-D-18). Every
// route object has an id (`SF-nn`, `SF-nn:<slug>` or `X:<slug>`) and a handle `{sf, screen, titleKey}`.
// `/` redirects to the landing route and keeps the search string. The authenticated branch
// (X:session) loads the session and gates MFA enrolment; inside it the shell (X:shell) renders the
// screens through the route error boundary (X:route-error), and unknown paths render X:not-found.
// Screen items add their route objects to the lists below in SCREENS §0.4 order.
import type { QueryClient } from "@tanstack/react-query";
import {
  createBrowserRouter,
  type DataRouter,
  parsePath,
  redirect,
  type RouteObject,
  type RouterNavigateOptions,
  type To,
} from "react-router";

import { accessOf } from "../lib/access";
import { fetchMe } from "../lib/api/queries/me";
import { fetchTenant, tenantKey } from "../lib/api/queries/tenant";
import { queryKeys } from "../lib/api/query-keys";
import {
  fetchSession,
  RequireSession,
  SESSION_ROUTE_ID,
  SessionPending,
  sessionLoader,
} from "./auth/RequireSession";
import { NotFound, ParamGuard } from "./errors/NotFound";
import { RouteError } from "./errors/RouteError";
import { AppShell, type RouteHandle } from "./shell/AppShell";

export type { RouteHandle } from "./shell/AppShell";

/** Public routes outside the session: the SF-22 family (SCREENS RT-01, RT-02, RT-05, RT-111, RT-112). */
export const PUBLIC_ROUTES: readonly RouteObject[] = [
  {
    id: "SF-22",
    path: "/sign-in",
    handle: { sf: "SF-22", screen: "SF-22", titleKey: "auth.sign-in.title" },
    HydrateFallback: SessionPending,
    lazy: async () => ({ Component: (await import("../routes/auth/sign-in")).SignIn }),
  },
  {
    id: "SF-22:mfa-challenge",
    path: "/sign-in/mfa",
    handle: { sf: "SF-22", screen: "SF-22:mfa-challenge", titleKey: "auth.mfa-challenge.title" },
    HydrateFallback: SessionPending,
    lazy: async () => ({
      Component: (await import("../routes/auth/mfa-challenge")).MfaChallenge,
    }),
  },
  {
    // SCREENS RT-05 SF-22:accept-invitation: the token rides in the URL fragment (BUILD_SPEC WEB-13).
    id: "SF-22:accept-invitation",
    path: "/accept-invitation",
    handle: {
      sf: "SF-22",
      screen: "SF-22:accept-invitation",
      titleKey: "auth.accept-invitation.title",
    },
    HydrateFallback: SessionPending,
    lazy: async () => ({
      Component: (await import("../routes/auth/accept-invitation")).AcceptInvitation,
    }),
  },
  {
    // SCREENS RT-111 SF-22:password-reset (BUILD_SPEC WEB-14).
    id: "SF-22:password-reset",
    path: "/password/reset",
    handle: { sf: "SF-22", screen: "SF-22:password-reset", titleKey: "auth.password-reset.title" },
    HydrateFallback: SessionPending,
    lazy: async () => ({
      Component: (await import("../routes/auth/password-reset")).PasswordReset,
    }),
  },
  {
    // SCREENS RT-112 SF-22:password-reset-confirm: the token rides in the URL fragment.
    id: "SF-22:password-reset-confirm",
    path: "/password/reset/confirm",
    handle: {
      sf: "SF-22",
      screen: "SF-22:password-reset-confirm",
      titleKey: "auth.password-reset-confirm.title",
    },
    HydrateFallback: SessionPending,
    lazy: async () => ({
      Component: (await import("../routes/auth/password-reset-confirm")).PasswordResetConfirm,
    }),
  },
];

/** Authenticated routes outside the shell (SCREENS RT-03, RT-04, RT-06). */
export const SESSION_ROUTES: readonly RouteObject[] = [
  {
    // SCREENS RT-03 SF-22:mfa-enrol, the MfaGate target (REQ-PLT-005; BUILD_SPEC WEB-13).
    id: "SF-22:mfa-enrol",
    path: "/mfa/enrol",
    handle: { sf: "SF-22", screen: "SF-22:mfa-enrol", titleKey: "auth.mfa-enrol.title" },
    lazy: async () => ({ Component: (await import("../routes/auth/mfa-enrol")).MfaEnrol }),
  },
  {
    // SCREENS RT-04 SF-22:password-change (BUILD_SPEC WEB-14).
    id: "SF-22:password-change",
    path: "/password/change",
    handle: {
      sf: "SF-22",
      screen: "SF-22:password-change",
      titleKey: "auth.password-change.title",
    },
    lazy: async () => ({
      Component: (await import("../routes/auth/password-change")).PasswordChange,
    }),
  },
  {
    id: "SF-23:select",
    path: "/select-workspace",
    handle: { sf: "SF-23", screen: "SF-23:select", titleKey: "onboarding.select-workspace.title" },
    lazy: async () => ({
      Component: (await import("../routes/onboarding/select-workspace")).SelectWorkspace,
    }),
  },
];

/** SCREENS RT-59 SF-13:revenue, the target of `/policies`. */
export const POLICIES_LANDING_PATH = "/policies/revenue";

/** Routes inside the shell, in SCREENS §0.4 order. */
export const SCREEN_ROUTES: readonly RouteObject[] = [
  {
    // SCREENS RT-07 SF-01, the "Home" rail destination and the BS-D-08 landing route (BUILD_SPEC RPS-22).
    id: "SF-01",
    path: "/home",
    handle: { sf: "SF-01", screen: "SF-01", titleKey: "home.page.title" },
    lazy: async () => ({ Component: (await import("../routes/home/home")).HomePage }),
  },
  {
    // SCREENS RT-08 SF-02, the "Contracts" rail destination.
    id: "SF-02",
    path: "/contracts",
    handle: { sf: "SF-02", screen: "SF-02", titleKey: "contracts.list.title" },
    lazy: async () => ({ Component: (await import("../routes/contracts/list")).ContractsList }),
  },
  {
    // SCREENS RT-09 SF-03:new (BUILD_SPEC CTR-24): the static segment ranks above `:contractId`.
    id: "SF-03:new",
    path: "/contracts/new",
    handle: { sf: "SF-03", screen: "SF-03:new", titleKey: "contracts.draft.new.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/draft-form")).NewContract,
    }),
  },
  {
    // SCREENS RT-10: `/contracts/:contractId` redirects to the Obligations tab and keeps the search.
    id: "X:contract-redirect",
    path: "/contracts/:contractId",
    handle: {
      sf: "X",
      screen: "X:contract-redirect",
      titleKey: "contracts.workbench.documentTitle",
    },
    loader: ({ params, request }) =>
      redirect(`/contracts/${params.contractId ?? ""}/obligations${new URL(request.url).search}`),
  },
  {
    // SCREENS RT-10 SF-03 and RT-11 SF-03:obligation: one workbench, so selecting an obligation keeps
    // the frame mounted; the child route carries the pane's id and handle.
    id: "SF-03",
    path: "/contracts/:contractId/obligations",
    handle: { sf: "SF-03", screen: "SF-03", titleKey: "contracts.workbench.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
    children: [
      {
        id: "SF-03:obligation",
        path: ":obligationId",
        handle: {
          sf: "SF-03",
          screen: "SF-03:obligation",
          titleKey: "contracts.workbench.obligationDocumentTitle",
        },
      },
    ],
  },
  {
    // SCREENS RT-12 SF-03:estimates and RT-13 SF-03:estimate (BUILD_SPEC CTR-25): the workbench frame
    // with the estimates master list; the child route carries the selected element.
    id: "SF-03:estimates",
    path: "/contracts/:contractId/estimates",
    handle: {
      sf: "SF-03",
      screen: "SF-03:estimates",
      titleKey: "contracts.estimates.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
    children: [
      {
        id: "SF-03:estimate",
        path: ":estimateId",
        handle: {
          sf: "SF-03",
          screen: "SF-03:estimate",
          titleKey: "contracts.estimates.estimateDocumentTitle",
        },
      },
    ],
  },
  {
    // SCREENS RT-14 SF-03:schedules, RT-15 SF-03:billing and RT-16 SF-03:journals: the workbench frame
    // with the tab's panels (BUILD_SPEC CTR-23).
    id: "SF-03:schedules",
    path: "/contracts/:contractId/schedules",
    handle: {
      sf: "SF-03",
      screen: "SF-03:schedules",
      titleKey: "contracts.schedules.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
  },
  {
    id: "SF-03:billing",
    path: "/contracts/:contractId/billing",
    handle: { sf: "SF-03", screen: "SF-03:billing", titleKey: "contracts.billing.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
  },
  {
    id: "SF-03:journals",
    path: "/contracts/:contractId/journals",
    handle: {
      sf: "SF-03",
      screen: "SF-03:journals",
      titleKey: "contracts.journals.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
  },
  {
    // SCREENS RT-17 SF-03:modifications and RT-18 SF-03:history: the workbench frame with the tab's
    // panel (BUILD_SPEC CTR-24).
    id: "SF-03:modifications",
    path: "/contracts/:contractId/modifications",
    handle: {
      sf: "SF-03",
      screen: "SF-03:modifications",
      titleKey: "contracts.modifications.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
  },
  {
    id: "SF-03:history",
    path: "/contracts/:contractId/history",
    handle: { sf: "SF-03", screen: "SF-03:history", titleKey: "contracts.history.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/workbench")).ContractWorkbench,
    }),
  },
  {
    // SCREENS RT-19 SF-03:edit (BUILD_SPEC CTR-24). The form opens behind the guard of ruling R-93 (a)
    // until a read answers the draft as it stands (item CTR-DRAFT-READ-1).
    id: "SF-03:edit",
    path: "/contracts/:contractId/edit",
    handle: { sf: "SF-03", screen: "SF-03:edit", titleKey: "contracts.draft.edit.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/draft-form")).EditDraft,
    }),
  },
  {
    // SCREENS RT-20 SF-07 (BUILD_SPEC CTR-27): step "Change" of a modification that does not exist
    // yet; the static segment ranks above `:modificationId`.
    id: "SF-07",
    path: "/contracts/:contractId/modifications/new",
    handle: { sf: "SF-07", screen: "SF-07", titleKey: "modifications.wizard.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/contracts/modification-wizard")).ModificationWizard,
    }),
  },
  {
    // SCREENS RT-21 SF-07:detail: the wizard of a DRAFT, the read-only detail of any other status.
    id: "SF-07:detail",
    path: "/contracts/:contractId/modifications/:modificationId",
    handle: {
      sf: "SF-07",
      screen: "SF-07:detail",
      titleKey: "modifications.detail.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/contracts/modification-detail")).ModificationDetail,
    }),
  },
  {
    // SCREENS_B RT-25 SF-04, the "Schedules" rail destination (BUILD_SPEC RPS-7).
    id: "SF-04",
    path: "/schedules",
    handle: { sf: "SF-04", screen: "SF-04", titleKey: "schedules.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/schedules/schedules")).Schedules }),
  },
  {
    // SCREENS_B §1.1: `/close` redirects to the context entity, primary book and earliest open period
    // (BR-UX-01); the "Close" rail destination (BUILD_SPEC CLO-23).
    id: "X:close-redirect",
    path: "/close",
    handle: { sf: "X", screen: "X:close-redirect", titleKey: "close.cockpit.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/close/cockpit")).CloseRedirect }),
  },
  {
    // SCREENS RT-26 SF-05 and RT-100 SF-05:journal-preview: one cockpit frame with the tab's content.
    id: "SF-05",
    path: "/close/:entity/:book/:period",
    handle: { sf: "SF-05", screen: "SF-05", titleKey: "close.cockpit.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/close/cockpit")).CloseCockpitPage,
    }),
  },
  {
    // SCREENS RT-99 SF-05:close-run: the cockpit frame with the Close run tab (BUILD_SPEC CLO-24).
    id: "SF-05:close-run",
    path: "/close/:entity/:book/:period/close-run",
    handle: { sf: "SF-05", screen: "SF-05:close-run", titleKey: "close.run.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/close/close-run")).CloseRunPage,
    }),
  },
  {
    id: "SF-05:journal-preview",
    path: "/close/:entity/:book/:period/journal-preview",
    handle: {
      sf: "SF-05",
      screen: "SF-05:journal-preview",
      titleKey: "close.journalPreview.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/close/journal-preview")).JournalPreviewPage,
    }),
  },
  {
    // SCREENS RT-102 SF-05:reconciliations: the cockpit frame with the Reconciliations tab (BUILD_SPEC
    // CLO-25).
    id: "SF-05:reconciliations",
    path: "/close/:entity/:book/:period/reconciliations",
    handle: {
      sf: "SF-05",
      screen: "SF-05:reconciliations",
      titleKey: "close.reconciliations.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/close/reconciliations")).ReconciliationsPage,
    }),
  },
  {
    // SCREENS RT-103 SF-05:reconciliation: one reconciliation as its own record page (SCREENS_B §2.2).
    id: "SF-05:reconciliation",
    path: "/close/:entity/:book/:period/reconciliations/:reconciliationId",
    handle: {
      sf: "SF-05",
      screen: "SF-05:reconciliation",
      titleKey: "close.reconciliation.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/close/reconciliation")).ReconciliationPage,
    }),
  },
  {
    // SCREENS RT-101 SF-05:history: the cockpit frame with the History tab (BUILD_SPEC CLO-24).
    id: "SF-05:history",
    path: "/close/:entity/:book/:period/history",
    handle: { sf: "SF-05", screen: "SF-05:history", titleKey: "close.history.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/close/history")).CloseHistoryPage,
    }),
  },
  {
    // SCREENS RT-27 SF-05:multi-entity: close runs for several entities of one period (BUILD_SPEC
    // CLO-24). One segment after `/close`, so it never meets the cockpit's three.
    id: "SF-05:multi-entity",
    path: "/close/multi-entity",
    handle: { sf: "SF-05", screen: "SF-05:multi-entity", titleKey: "close.multi.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/close/multi-entity")).MultiEntityClosePage,
    }),
  },
  {
    // SCREENS RT-28 SF-06, the "Journals" rail destination (BUILD_SPEC CLO-26).
    id: "SF-06",
    path: "/journals",
    handle: { sf: "SF-06", screen: "SF-06", titleKey: "journals.runs.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/journals/journal-runs")).JournalRuns,
    }),
  },
  {
    // SCREENS RT-29 SF-06:run, RT-104 SF-06:run-lines and RT-105 SF-06:run-batches: one run frame with
    // the tab's content.
    id: "SF-06:run",
    path: "/journals/runs/:runId",
    handle: { sf: "SF-06", screen: "SF-06:run", titleKey: "journals.run.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/journals/run")).JournalRunSummaryPage,
    }),
  },
  {
    // SCREENS_B RT-30 SF-06:entries Journal entries by date range (BUILD_SPEC RPS-7).
    id: "SF-06:entries",
    path: "/journals/entries",
    handle: { sf: "SF-06", screen: "SF-06:entries", titleKey: "journals.entries.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/journals/entries")).JournalEntries,
    }),
  },
  {
    id: "SF-06:run-lines",
    path: "/journals/runs/:runId/lines",
    handle: { sf: "SF-06", screen: "SF-06:run-lines", titleKey: "journals.lines.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/journals/run-lines")).JournalRunLinesPage,
    }),
  },
  {
    id: "SF-06:run-batches",
    path: "/journals/runs/:runId/batches",
    handle: {
      sf: "SF-06",
      screen: "SF-06:run-batches",
      titleKey: "journals.batches.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/journals/run-batches")).JournalRunBatchesPage,
    }),
  },
  {
    // SCREENS_B RT-31 SF-08, the "Reports" rail destination (BUILD_SPEC RPS-6).
    id: "SF-08",
    path: "/reports",
    handle: { sf: "SF-08", screen: "SF-08", titleKey: "reports.catalogue.documentTitle" },
    lazy: async () => ({
      Component: (await import("../routes/reports/catalogue")).ReportCatalogue,
    }),
  },
  {
    // SCREENS_B RT-32 SF-08:report Report view (RV-01 to RV-14).
    id: "SF-08:report",
    path: "/reports/:reportCode",
    handle: { sf: "SF-08", screen: "SF-08:report", titleKey: "reports.report.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/reports/report")).ReportView }),
  },
  {
    // SCREENS_B RT-106 SF-08:runs Report run register (BUILD_SPEC RPS-18): `f.*` and saved views.
    id: "SF-08:runs",
    path: "/reports/runs",
    handle: { sf: "SF-08", screen: "SF-08:runs", titleKey: "reports.runs.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/reports/runs")).ReportRuns }),
  },
  {
    // SCREENS_B RT-33 SF-08:run Report run record, where a rerun opens the new run.
    id: "SF-08:run",
    path: "/reports/runs/:runId",
    handle: { sf: "SF-08", screen: "SF-08:run", titleKey: "reports.run.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/reports/run")).ReportRunPage }),
  },
  {
    // SCREENS_B RT-107 SF-08:dashboard (BUILD_SPEC RPS-19): `run.<panel>` (SCR-URL-26); a code without a
    // dashboard is X:not-found before the page renders.
    id: "SF-08:dashboard",
    path: "/reports/dashboards/:dashboardCode",
    handle: { sf: "SF-08", screen: "SF-08:dashboard", titleKey: "reports.dashboard.documentTitle" },
    lazy: async () => {
      const page = await import("../routes/reports/dashboard");
      return { Component: page.DashboardPage, loader: page.dashboardLoader };
    },
  },
  {
    // SCREENS_B RT-37 SF-09:audit-log (BUILD_SPEC RPS-21): `f.*`, `drawer=event` with `event`.
    id: "SF-09:audit-log",
    path: "/reports/audit-log",
    handle: { sf: "SF-09", screen: "SF-09:audit-log", titleKey: "evidence.auditLog.title" },
    lazy: async () => ({ Component: (await import("../routes/evidence/audit-log")).AuditLog }),
  },
  {
    // SCREENS_B RT-38 SF-09:verification, the NTF-09 link target.
    id: "SF-09:verification",
    path: "/reports/audit-log/verifications/:verificationId",
    handle: {
      sf: "SF-09",
      screen: "SF-09:verification",
      titleKey: "evidence.verification.title",
    },
    lazy: async () => ({
      Component: (await import("../routes/evidence/verification")).VerificationPage,
    }),
  },
  {
    // SCREENS RT-42 SF-10, the "Data" rail destination (SCR-IA-01; BUILD_SPEC DIN-15).
    id: "SF-10",
    path: "/data/imports",
    handle: { sf: "SF-10", screen: "SF-10", titleKey: "data.imports.title" },
    lazy: async () => ({ Component: (await import("../routes/data/imports")).ImportsList }),
  },
  {
    // SCREENS RT-43 SF-10:new and RT-44 SF-10:detail (BUILD_SPEC DIN-16): `/data/imports/:importId`
    // redirects to the step of the import's status.
    id: "SF-10:new",
    path: "/data/imports/new",
    handle: { sf: "SF-10", screen: "SF-10:new", titleKey: "data.imports.new.title" },
    lazy: async () => ({ Component: (await import("../routes/data/import-new")).ImportNew }),
  },
  {
    id: "X:import-redirect",
    path: "/data/imports/:importId",
    handle: {
      sf: "X",
      screen: "X:import-redirect",
      titleKey: "data.imports.detail.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/data/import-detail")).ImportRedirect,
    }),
  },
  {
    id: "SF-10:detail",
    path: "/data/imports/:importId/:step",
    handle: { sf: "SF-10", screen: "SF-10:detail", titleKey: "data.imports.detail.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/data/import-detail")).ImportDetail }),
  },
  {
    id: "SF-10:templates",
    path: "/data/templates",
    handle: { sf: "SF-10", screen: "SF-10:templates", titleKey: "data.templates.title" },
    lazy: async () => ({ Component: (await import("../routes/data/templates")).ImportTemplates }),
  },
  {
    // SCREENS RT-46 SF-11 and RT-47 SF-11:item (BUILD_SPEC DIN-17): one queue, so selecting an item
    // keeps the frame and its filters mounted; the child route carries the item's id and handle.
    id: "SF-11",
    path: "/data/exceptions",
    handle: { sf: "SF-11", screen: "SF-11", titleKey: "data.exceptions.title" },
    lazy: async () => ({ Component: (await import("../routes/data/exceptions")).ExceptionQueue }),
    children: [
      {
        id: "SF-11:item",
        path: ":exceptionId",
        handle: { sf: "SF-11", screen: "SF-11:item", titleKey: "data.exceptions.documentTitle" },
      },
    ],
  },
  {
    // SCREENS RT-48 SF-16, RT-49 SF-16:connection (`pane=settings|sync-runs|external-ids`) and RT-50
    // SF-16:sync-run (BUILD_SPEC DIN-18).
    id: "SF-16",
    path: "/data/integrations",
    handle: { sf: "SF-16", screen: "SF-16", titleKey: "data.integrations.title" },
    lazy: async () => ({
      Component: (await import("../routes/data/integrations")).IntegrationsList,
    }),
  },
  {
    id: "SF-16:connection",
    path: "/data/integrations/:connectionId",
    handle: {
      sf: "SF-16",
      screen: "SF-16:connection",
      titleKey: "data.integrations.connection.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/data/integration-connection")).IntegrationConnection,
    }),
  },
  {
    id: "SF-16:sync-run",
    path: "/data/integrations/:connectionId/sync-runs/:syncRunId",
    handle: {
      sf: "SF-16",
      screen: "SF-16:sync-run",
      titleKey: "data.integrations.syncRun.documentTitle",
    },
    lazy: async () => ({ Component: (await import("../routes/data/sync-run")).SyncRunPage }),
  },
  {
    // SCREENS_B RT-53 SF-19:detail (§10.3; F-ADM WEB item for SCREENS_B 1.20, supervisor option A):
    // the screen parameter `step` selects the step; the Mapping and Import steps of the opening-balances
    // journey are built, the other steps and SF-19 (list) / SF-19:new are separate WEB items.
    id: "SF-19:detail",
    path: "/data/migrations/:migrationId",
    handle: {
      sf: "SF-19",
      screen: "SF-19:detail",
      titleKey: "data.migrations.detail.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/data/migration-detail")).MigrationDetail,
    }),
  },
  {
    id: "SF-12",
    path: "/approvals",
    handle: { sf: "SF-12", screen: "SF-12", titleKey: "approvals.title" },
    lazy: async () => ({ Component: (await import("../routes/approvals/inbox")).WaitingForMe }),
  },
  {
    id: "SF-12:submitted",
    path: "/approvals/submitted",
    handle: { sf: "SF-12", screen: "SF-12:submitted", titleKey: "approvals.tabs.submitted" },
    lazy: async () => ({ Component: (await import("../routes/approvals/inbox")).SubmittedByMe }),
  },
  {
    id: "SF-12:all",
    path: "/approvals/all",
    handle: { sf: "SF-12", screen: "SF-12:all", titleKey: "approvals.tabs.all" },
    lazy: async () => ({ Component: (await import("../routes/approvals/inbox")).AllRequests }),
  },
  {
    id: "SF-12:request",
    path: "/approvals/requests/:requestId",
    handle: { sf: "SF-12", screen: "SF-12:request", titleKey: "approvals.title" },
    lazy: async () => ({
      Component: (await import("../routes/approvals/request")).ApprovalRequest,
    }),
  },
  {
    // SCREENS RT-58 SF-12:delegations (BUILD_SPEC WEB-16).
    id: "SF-12:delegations",
    path: "/approvals/delegations",
    handle: {
      sf: "SF-12",
      screen: "SF-12:delegations",
      titleKey: "approvals.tabs.delegations",
    },
    lazy: async () => ({
      Component: (await import("../routes/approvals/delegations")).Delegations,
    }),
  },
  {
    // SCREENS RT-59: `/policies` redirects to the first Policies tab (SCR-IA-01).
    id: "SF-13",
    path: "/policies",
    handle: { sf: "SF-13", screen: "SF-13", titleKey: "policies.title" },
    loader: () => redirect(POLICIES_LANDING_PATH),
  },
  {
    id: "SF-13:revenue",
    path: POLICIES_LANDING_PATH,
    handle: { sf: "SF-13", screen: "SF-13:revenue", titleKey: "policies.tabs.revenue" },
    lazy: async () => ({ Component: (await import("../routes/policies/revenue")).RevenuePolicies }),
  },
  {
    id: "SF-13:control-rules",
    path: "/policies/control-rules",
    handle: { sf: "SF-13", screen: "SF-13:control-rules", titleKey: "policies.tabs.controlRules" },
    lazy: async () => ({
      Component: (await import("../routes/policies/control-rules")).ControlRules,
    }),
  },
  {
    // SCREENS RT-61 SF-13:template-version (BUILD_SPEC RFD-23): `pane=outputs|policy-values|tests|simulation|changes`.
    id: "SF-13:template-version",
    path: "/policies/templates/:templateId/versions/:versionId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:template-version",
      titleKey: "policies.templateVersion.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/template-version")).TemplateVersionEditor,
    }),
  },
  {
    id: "SF-13:rule-set-version",
    path: "/policies/rule-sets/:ruleSetId/versions/:versionId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:rule-set-version",
      titleKey: "policies.version.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/rule-set-version")).RuleSetVersionEditor,
    }),
  },
  {
    // SCREENS RT-63 SF-13:accounting (BUILD_SPEC RFD-23).
    id: "SF-13:accounting",
    path: "/policies/accounting",
    handle: { sf: "SF-13", screen: "SF-13:accounting", titleKey: "policies.tabs.accounting" },
    lazy: async () => ({
      Component: (await import("../routes/policies/accounting")).AccountingPolicies,
    }),
  },
  {
    // SCREENS RT-64 SF-13:accounting-version.
    id: "SF-13:accounting-version",
    path: "/policies/accounting/:policyId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:accounting-version",
      titleKey: "policies.accountingVersion.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/accounting-version")).AccountingVersionEditor,
    }),
  },
  {
    id: "SF-13:ssp-books",
    path: "/policies/ssp-books",
    handle: { sf: "SF-13", screen: "SF-13:ssp-books", titleKey: "policies.tabs.sspBooks" },
    lazy: async () => ({ Component: (await import("../routes/policies/ssp-books")).SspBooks }),
  },
  {
    // SCREENS RT-66: `/policies/ssp-books/:bookId` redirects to the current approved version, else
    // the draft (L4-5-Q-51).
    id: "SF-13:ssp-book",
    path: "/policies/ssp-books/:bookId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:ssp-book",
      titleKey: "policies.sspVersion.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/ssp-books")).SspBookRedirect,
    }),
  },
  {
    id: "SF-13:ssp-book-version",
    path: "/policies/ssp-books/:bookId/versions/:versionId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:ssp-book-version",
      titleKey: "policies.sspVersion.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/ssp-book-version")).SspBookVersionEditor,
    }),
  },
  {
    id: "SF-13:ssp-calculator",
    path: "/policies/ssp-calculator",
    handle: {
      sf: "SF-13",
      screen: "SF-13:ssp-calculator",
      titleKey: "policies.tabs.sspCalculator",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/ssp-calculator")).SspCalculator,
    }),
  },
  {
    id: "SF-13:ssp-calculator-run",
    path: "/policies/ssp-calculator/runs/:runId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:ssp-calculator-run",
      titleKey: "policies.sspRun.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/ssp-calculator-run")).SspCalculatorRunPage,
    }),
  },
  {
    // SCREENS RT-69 SF-13:account-mapping (BUILD_SPEC RFD-25).
    id: "SF-13:account-mapping",
    path: "/policies/account-mapping",
    handle: {
      sf: "SF-13",
      screen: "SF-13:account-mapping",
      titleKey: "policies.tabs.accountMapping",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/account-mapping")).AccountMappings,
    }),
  },
  {
    // SCREENS RT-70 SF-13:account-mapping-version (`pane=rules|coverage|resolve|simulation|changes`).
    id: "SF-13:account-mapping-version",
    path: "/policies/account-mapping/:mappingVersionId",
    handle: {
      sf: "SF-13",
      screen: "SF-13:account-mapping-version",
      titleKey: "policies.mappingVersion.documentTitle",
    },
    lazy: async () => ({
      Component: (await import("../routes/policies/account-mapping-version"))
        .AccountMappingVersionEditor,
    }),
  },
  {
    id: "SF-15",
    path: "/settings",
    handle: { sf: "SF-15", screen: "SF-15", titleKey: "settings.index.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/index")).SettingsIndex }),
  },
  {
    id: "SF-15:notifications",
    path: "/settings/notifications",
    handle: {
      sf: "SF-15",
      screen: "SF-15:notifications",
      titleKey: "settings.notifications.title",
    },
    lazy: async () => ({
      Component: (await import("../routes/settings/notifications")).NotificationPreferences,
    }),
  },
  {
    id: "SF-15:profile",
    path: "/settings/profile",
    handle: { sf: "SF-15", screen: "SF-15:profile", titleKey: "settings.profile.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/profile")).Profile }),
  },
  {
    id: "SF-15:setup",
    path: "/settings/setup",
    handle: { sf: "SF-15", screen: "SF-15:setup", titleKey: "settings.setup.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/setup")).WorkspaceSetup }),
  },
  {
    // SCREENS RT-75 SF-15:entities (BUILD_SPEC RFD-18).
    id: "SF-15:entities",
    path: "/settings/entities",
    handle: { sf: "SF-15", screen: "SF-15:entities", titleKey: "settings.entities.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/entities")).EntitiesScreen }),
  },
  {
    // SCREENS RT-76 SF-15:calendars (BUILD_SPEC RFD-18): `calendar=<code>`, `f.fiscal_year`.
    id: "SF-15:calendars",
    path: "/settings/calendars",
    handle: { sf: "SF-15", screen: "SF-15:calendars", titleKey: "settings.calendars.title" },
    lazy: async () => ({
      Component: (await import("../routes/settings/calendars")).CalendarsScreen,
    }),
  },
  {
    // SCREENS RT-77 SF-15:currencies (BUILD_SPEC RFD-18): `rate_set=<code>`, `version=<n>`.
    id: "SF-15:currencies",
    path: "/settings/currencies",
    handle: { sf: "SF-15", screen: "SF-15:currencies", titleKey: "settings.currencies.title" },
    lazy: async () => ({
      Component: (await import("../routes/settings/currencies")).CurrenciesScreen,
    }),
  },
  {
    id: "SF-15:chart-of-accounts",
    path: "/settings/chart-of-accounts",
    handle: {
      sf: "SF-15",
      screen: "SF-15:chart-of-accounts",
      titleKey: "settings.chartOfAccounts.title",
    },
    lazy: async () => ({
      Component: (await import("../routes/settings/chart-of-accounts")).ChartOfAccounts,
    }),
  },
  {
    // SCREENS RT-79 SF-15:customers (BUILD_SPEC RFD-20).
    id: "SF-15:customers",
    path: "/settings/customers",
    handle: { sf: "SF-15", screen: "SF-15:customers", titleKey: "settings.customers.title" },
    lazy: async () => ({
      Component: (await import("../routes/settings/customers")).CustomersScreen,
    }),
  },
  {
    // SCREENS RT-80 SF-15:customer.
    id: "SF-15:customer",
    path: "/settings/customers/:customerId",
    handle: { sf: "SF-15", screen: "SF-15:customer", titleKey: "settings.customer.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/customer")).CustomerPage }),
  },
  {
    // SCREENS RT-81 SF-15:related-party-groups.
    id: "SF-15:related-party-groups",
    path: "/settings/related-party-groups",
    handle: {
      sf: "SF-15",
      screen: "SF-15:related-party-groups",
      titleKey: "settings.relatedParty.title",
    },
    lazy: async () => ({
      Component: (await import("../routes/settings/related-party-groups")).RelatedPartyGroupsScreen,
    }),
  },
  {
    // SCREENS RT-82 SF-15:products (BUILD_SPEC RFD-21).
    id: "SF-15:products",
    path: "/settings/products",
    handle: { sf: "SF-15", screen: "SF-15:products", titleKey: "settings.products.title" },
    lazy: async () => ({
      Component: (await import("../routes/settings/products")).ProductsScreen,
    }),
  },
  {
    // SCREENS RT-83 SF-15:product (`pane=attributes|bundle|ssp|policy-values`).
    id: "SF-15:product",
    path: "/settings/products/:productId",
    handle: { sf: "SF-15", screen: "SF-15:product", titleKey: "settings.product.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/product")).ProductPage }),
  },
  {
    // SCREENS RT-95 SF-24:results (BUILD_SPEC CTR-28): `/search?q=<query>&f.scope=is:<scope>`, the page
    // "Show all results" of the command palette opens.
    id: "SF-24:results",
    path: "/search",
    handle: { sf: "SF-24", screen: "SF-24:results", titleKey: "search.results.title" },
    lazy: async () => ({ Component: (await import("../routes/search/results")).SearchResults }),
  },
  {
    // SCREENS RT-96 X:trace: the calculation trace of a figure, opened from the Explain panel (CTR-26).
    id: "X:trace",
    path: "/trace/:calcTraceId",
    handle: { sf: "X", screen: "X:trace", titleKey: "explain.trace.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/trace/trace")).CalculationTrace }),
  },
  {
    id: "SF-15:workspace",
    path: "/settings/workspace",
    handle: { sf: "SF-15", screen: "SF-15:workspace", titleKey: "settings.workspace.title" },
    lazy: async () => ({
      Component: (await import("../routes/settings/workspace")).WorkspaceSettings,
    }),
  },
  {
    // SCREENS RT-84 SF-15:sandbox (BUILD_SPEC SNP-5).
    id: "SF-15:sandbox",
    path: "/settings/sandbox",
    handle: { sf: "SF-15", screen: "SF-15:sandbox", titleKey: "settings.sandbox.title" },
    lazy: async () => ({ Component: (await import("../routes/settings/sandbox")).SandboxCopies }),
  },
  {
    // SCREENS RT-87 SF-14 and RT-108 SF-14:user (BUILD_SPEC WEB-19).
    id: "SF-14",
    path: "/settings/users",
    handle: { sf: "SF-14", screen: "SF-14", titleKey: "access.users.title" },
    lazy: async () => ({ Component: (await import("../routes/access/users")).UsersList }),
  },
  {
    // SCREENS RT-88 SF-14:roles and RT-89 SF-14:sod (BUILD_SPEC WEB-20).
    id: "SF-14:roles",
    path: "/settings/roles",
    handle: { sf: "SF-14", screen: "SF-14:roles", titleKey: "access.roles.title" },
    lazy: async () => ({ Component: (await import("../routes/access/roles")).RolesScreen }),
  },
  {
    id: "SF-14:sod",
    path: "/settings/separation-of-duties",
    handle: { sf: "SF-14", screen: "SF-14:sod", titleKey: "access.sod.title" },
    lazy: async () => ({ Component: (await import("../routes/access/sod")).SodScreen }),
  },
  {
    // SCREENS RT-90 SF-14:access-reviews (BUILD_SPEC WEB-21).
    id: "SF-14:access-reviews",
    path: "/settings/access-reviews",
    handle: { sf: "SF-14", screen: "SF-14:access-reviews", titleKey: "access.reviews.title" },
    lazy: async () => ({
      Component: (await import("../routes/access/access-reviews")).AccessReviewsScreen,
    }),
  },
  {
    // SCREENS RT-91 SF-14:security (BUILD_SPEC WEB-22; the "Sessions" form follows API-R-13, BS1-D-15).
    id: "SF-14:security",
    path: "/settings/security",
    handle: { sf: "SF-14", screen: "SF-14:security", titleKey: "access.security.title" },
    lazy: async () => ({ Component: (await import("../routes/access/security")).SecurityScreen }),
  },
  {
    // SCREENS RT-92 SF-14:support-access (BUILD_SPEC WEB-22).
    id: "SF-14:support-access",
    path: "/settings/support-access",
    handle: { sf: "SF-14", screen: "SF-14:support-access", titleKey: "access.supportAccess.title" },
    lazy: async () => ({
      Component: (await import("../routes/access/support-access")).SupportAccessScreen,
    }),
  },
  {
    id: "SF-14:user",
    path: "/settings/users/:membershipId",
    handle: { sf: "SF-14", screen: "SF-14:user", titleKey: "access.user.documentTitle" },
    lazy: async () => ({ Component: (await import("../routes/access/user")).UserPage }),
  },
  {
    // SCREENS RT-109 SF-14:access-review.
    id: "SF-14:access-review",
    path: "/settings/access-reviews/:reviewId",
    handle: { sf: "SF-14", screen: "SF-14:access-review", titleKey: "access.review.title" },
    lazy: async () => ({
      Component: (await import("../routes/access/access-review")).AccessReviewPage,
    }),
  },
  {
    // SCREENS RT-93 SF-16:developer (BUILD_SPEC WEB-23): `pane=api-clients|webhooks|openapi`.
    id: "SF-16:developer",
    path: "/settings/developer",
    handle: { sf: "SF-16", screen: "SF-16:developer", titleKey: "developer.title" },
    lazy: async () => ({
      Component: (await import("../routes/developer/developer")).DeveloperScreen,
    }),
  },
];

/** RT-97 X:design, mounted only when `VITE_EREV_DESIGN_GALLERY` is "1" (DS-VER-06). */
export const DESIGN_ROUTES: readonly RouteObject[] = [];

/** BS-D-08: SF-01 is built, so BS1-D-18 leaves only `/home` (BUILD_SPEC RPS-22). */
export const LANDING_ROUTES: readonly string[] = ["/home"];

/** SCREENS RT-74 SF-15:setup and the permission that lands there while setup is incomplete. */
export const SETUP_LANDING_PATH = "/settings/setup";
export const SETUP_LANDING_PERMISSION = "settings.manage";

/**
 * SCREENS_B §11.1 (J-01.1; PRD BR-PLT-02): a signed-in member of a workspace who holds
 * `settings.manage` while `setup_completed_at` is null lands on SF-15:setup instead of the landing
 * route, once that route is built. Any read that fails keeps the landing route.
 */
export async function landingTarget(
  queryClient: QueryClient,
  built: ReadonlySet<string>,
  home: string,
): Promise<string> {
  if (!built.has(SETUP_LANDING_PATH)) {
    return home;
  }
  try {
    const session = await queryClient.ensureQueryData({
      queryKey: queryKeys.session(),
      queryFn: fetchSession,
    });
    if (!session.authenticated || session.active_tenant === null) {
      return home;
    }
    if (session.mfa_required || session.mfa_enrolment_required) {
      // REQ-PLT-005: a session that owes its second factor reads nothing; the guard routes it on.
      return home;
    }
    const me = await queryClient.ensureQueryData({ queryKey: queryKeys.me(), queryFn: fetchMe });
    // `GET /tenant` answers a holder of the permission for all entities alone (04 API-C-03).
    if (!accessOf(me).holdsForAll(SETUP_LANDING_PERMISSION)) {
      return home;
    }
    const tenant = await queryClient.ensureQueryData({
      queryKey: tenantKey(),
      queryFn: fetchTenant,
    });
    return tenant.setup_completed_at === null ? SETUP_LANDING_PATH : home;
  } catch {
    return home;
  }
}

/** The first built landing candidate, else the last candidate (BS-D-08, BS1-D-18). */
export function landingRoute(
  built: ReadonlySet<string>,
  candidates: readonly string[] = LANDING_ROUTES,
): string {
  const fallback = candidates.at(-1);
  if (fallback === undefined) {
    throw new Error("LANDING_ROUTES needs at least one path (BS-D-08)");
  }
  return candidates.find((path) => built.has(path)) ?? fallback;
}

/** The absolute paths of route objects and their children; `*` routes add none. */
export function builtPaths(routes: readonly RouteObject[], parent = ""): ReadonlySet<string> {
  const paths = new Set<string>();
  for (const route of routes) {
    let base = parent;
    if (route.path !== undefined) {
      base = route.path.startsWith("/")
        ? route.path
        : `${parent.replace(/\/+$/, "")}/${route.path}`;
      if (!route.path.includes("*")) {
        paths.add(base);
      }
    }
    for (const path of builtPaths(route.children ?? [], base)) {
      paths.add(path);
    }
  }
  return paths;
}

/** RT-97: the design gallery routes only when the build flag is "1". */
export function designRoutes(
  flag: string | undefined,
  routes: readonly RouteObject[] = DESIGN_ROUTES,
): readonly RouteObject[] {
  return flag === "1" ? routes : [];
}

export interface RouteTableOptions {
  readonly queryClient: QueryClient;
  readonly publicRoutes?: readonly RouteObject[];
  readonly sessionRoutes?: readonly RouteObject[];
  readonly screenRoutes?: readonly RouteObject[];
  readonly designRoutes?: readonly RouteObject[];
}

function structural(screen: string, titleKey: string): RouteHandle {
  return { sf: "X", screen, titleKey };
}

export function buildRoutes({
  queryClient,
  publicRoutes = [],
  sessionRoutes = [],
  screenRoutes = [],
  designRoutes: gallery = [],
}: RouteTableOptions): RouteObject[] {
  const built = builtPaths([...publicRoutes, ...sessionRoutes, ...screenRoutes, ...gallery]);
  const home = landingRoute(built);
  return [
    {
      id: "X:landing",
      path: "/",
      handle: structural("X:landing", "shell.productName"),
      HydrateFallback: SessionPending,
      loader: async ({ request }) =>
        redirect(`${await landingTarget(queryClient, built, home)}${new URL(request.url).search}`),
    },
    ...publicRoutes,
    {
      id: SESSION_ROUTE_ID,
      handle: structural(SESSION_ROUTE_ID, "shell.productName"),
      HydrateFallback: SessionPending,
      loader: sessionLoader(queryClient),
      element: <RequireSession />,
      errorElement: <RouteError homePath={home} />,
      children: [
        ...sessionRoutes,
        {
          id: "X:shell",
          // The built paths also ride on the shell handle, so settings pages link built routes only.
          handle: { ...structural("X:shell", "shell.productName"), built },
          element: <AppShell built={built} homePath={home} />,
          children: [
            {
              id: "X:route-error",
              handle: structural("X:route-error", "errors.routeError.title"),
              element: <ParamGuard homePath={home} />,
              errorElement: <RouteError homePath={home} />,
              children: [
                ...screenRoutes,
                ...gallery,
                {
                  id: "X:not-found",
                  path: "*",
                  handle: structural("X:not-found", "errors.notFound.documentTitle"),
                  element: <NotFound homePath={home} />,
                },
              ],
            },
          ],
        },
      ],
    },
  ];
}

/** The production route table. */
export function appRoutes(queryClient: QueryClient): RouteObject[] {
  return buildRoutes({
    queryClient,
    publicRoutes: PUBLIC_ROUTES,
    sessionRoutes: SESSION_ROUTES,
    screenRoutes: SCREEN_ROUTES,
    designRoutes: designRoutes(import.meta.env.VITE_EREV_DESIGN_GALLERY),
  });
}

function namesNoPath(to: To): boolean {
  const { pathname } = typeof to === "string" ? parsePath(to) : to;
  return pathname === undefined || pathname === "";
}

/**
 * A control of a page that is leaving writes nothing (docs/dev-guide.md DG-FE-03 rev 1.215; SCREENS
 * §0.5 rev 1.40). Controls write view state as a navigation that names no path (`{ search }`,
 * "?…", "#…"), and the router resolves such a navigation against the address it holds at that
 * moment. A control still on screen after the router has moved on would therefore put its own
 * parameters on the next page's address. The navigation is dropped when the route it comes from
 * (`fromRouteId`, which `useNavigate` passes) is no longer among the matched routes. The guard knows
 * routes, not records: a page that stays on one route while its record changes is not caught.
 *
 * A page is leaving, too, while a navigation to another path is on its way (rev 1.230): the route is
 * still matched then, and a write without a path would land on the page being left and cancel the
 * member's navigation. It is dropped as well. A navigation on its way to the same path — a filter
 * being applied while a loader runs — drops nothing.
 */
export function guardLeavingPages<Router extends DataRouter>(router: Router): Router {
  const navigate = router.navigate.bind(router);
  const guarded = (to: To | number | null, options?: RouterNavigateOptions): Promise<void> => {
    if (typeof to === "number") {
      return navigate(to);
    }
    const from = options?.fromRouteId;
    if (to !== null && from !== undefined && namesNoPath(to)) {
      const { location, matches, navigation } = router.state;
      const onItsWayElsewhere =
        navigation.location !== undefined && navigation.location.pathname !== location.pathname;
      if (onItsWayElsewhere || !matches.some((match) => match.route.id === from)) {
        return Promise.resolve();
      }
    }
    return navigate(to, options);
  };
  router.navigate = guarded;
  return router;
}

export function createAppRouter(queryClient: QueryClient) {
  return guardLeavingPages(createBrowserRouter(appRoutes(queryClient)));
}
