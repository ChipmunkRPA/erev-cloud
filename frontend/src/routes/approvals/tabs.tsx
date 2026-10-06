// Approvals area header (SCREENS §0.3 SCR-IA-02 "Approvals"; §0.4 RT-54 to RT-58; §15.3; DESIGN_SYSTEM
// DS-CMP-07; BUILD_SPEC WEB-15, WEB-16). The `h1` "Approvals" and the route tabs "Waiting for me <n> ·
// Submitted by me · All requests · Delegations", shared by the three inbox views, the request inside its
// view and SF-12:delegations. The count beside "Waiting for me" is the binding's `X-Erev-Total-Count`,
// shown to a member who holds an approval permission. The Delegations tab renders when its route is
// built and the member holds an approval permission, RT-58's read permission (SCR-IA-02).
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { DELEGATIONS_ROUTE } from "../../lib/api/queries/approval-delegations";
import {
  APPROVAL_VIEWS,
  type ApprovalView,
  holdsApprovalPermission,
  useWaitingCount,
  VIEW_ROUTES,
} from "../../lib/api/queries/approvals";
import { useAccess } from "../../lib/access";
import { useMe } from "../../lib/api/queries/me";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";

export const DELEGATIONS_TAB = "delegations";

export interface ApprovalsHeaderProps {
  /**
   * The inbox view on screen and its own URL: its tab links there, so the tab stays the current page
   * while a request renders inside the view (SCREENS §15.1) and keeps the view's filter chips.
   */
  readonly current?: { readonly view: ApprovalView; readonly to: string } | undefined;
}

export function ApprovalsHeader({ current }: ApprovalsHeaderProps) {
  const me = useMe();
  const access = useAccess();
  const built = useBuiltPaths();
  const permitted = me.data === undefined || holdsApprovalPermission(access);
  const waiting = useWaitingCount(permitted);

  const tabs: RouteTab[] = APPROVAL_VIEWS.map((view) => ({
    id: view,
    label: t(`approvals.tabs.${view}`),
    count: view === "waiting" && permitted ? waiting.data : undefined,
    to: current?.view === view ? current.to : VIEW_ROUTES[view],
    end: true,
  }));
  if (built.has(DELEGATIONS_ROUTE) && me.data !== undefined && holdsApprovalPermission(access)) {
    tabs.push({
      id: DELEGATIONS_TAB,
      label: t("approvals.tabs.delegations"),
      to: DELEGATIONS_ROUTE,
      end: true,
    });
  }

  return (
    <>
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {t("approvals.title")}
      </h1>
      <RouteTabs label={t("approvals.tabs.label")} tabs={tabs} />
    </>
  );
}
