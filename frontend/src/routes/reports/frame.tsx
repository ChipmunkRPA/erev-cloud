// Reports area frame (SCREENS §0.3 SCR-IA-02; §0.4 RT-31, RT-35, RT-37, RT-39, RT-106; SCREENS_B §5
// introduction; DESIGN_SYSTEM DS-CMP-06, DS-CMP-07; BUILD_SPEC XR-14, RPS-21). The `h1` "Reports" and the
// route tabs Catalogue · Report runs · Evidence packs · Audit log · Scenarios and forecasts on the header
// strip of the area. A tab renders when its route is built and the user holds its read permission, and
// carries the context of the pill. Report views, run records and the verification record render their
// own `h1` with a breadcrumb instead. "Report runs" opens for `report.run` or `audit.read`, the two
// permissions the report routes admit (04 API-R-41 rev 1.128; BUILD_SPEC RPS-18).
import { useId } from "react";
import { useLocation } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { cn } from "../../components/ui/cn";
import { useAccess } from "../../lib/access";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";

export interface ReportsTab {
  readonly screen: string;
  readonly path: string;
  /** The message key under `reports.tabs`. */
  readonly key: string;
  /** The read permission of the route (SCREENS §0.4). */
  readonly permission: string;
  /** A second permission that opens the route as well. */
  readonly orPermission?: string;
}

/** SCREENS §0.3 SCR-IA-02 Reports route tabs, in order, with their §0.4 read permissions. */
export const REPORTS_TABS: readonly ReportsTab[] = [
  { screen: "SF-08", path: "/reports", key: "catalogue", permission: "report.run" },
  {
    screen: "SF-08:runs",
    path: "/reports/runs",
    key: "runs",
    permission: "report.run",
    orPermission: "audit.read",
  },
  { screen: "SF-09", path: "/reports/evidence", key: "evidence", permission: "report.run" },
  {
    screen: "SF-09:audit-log",
    path: "/reports/audit-log",
    key: "auditLog",
    permission: "audit.read",
  },
  { screen: "SF-17", path: "/reports/forecasts", key: "forecasts", permission: "scenario.use" },
];

/** SCREENS SCR-URL-01 to SCR-URL-03: the context a Reports tab keeps. */
const CONTEXT = ["entity", "period", "book"] as const;

/** The `h1` "Reports" with the route tabs of the built pages the user may read. */
export function ReportsHeader() {
  const titleId = useId();
  const location = useLocation();
  const built = useBuiltPaths();
  const access = useAccess();
  const search = contextSearch(location.search, CONTEXT);
  const tabs: RouteTab[] = REPORTS_TABS.filter(
    (tab) =>
      built.has(tab.path) &&
      (access.holdsAnywhere(tab.permission) ||
        (tab.orPermission !== undefined && access.holdsAnywhere(tab.orPermission))),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`reports.tabs.${tab.key}`),
    to: `${tab.path}${search}`,
    // The catalogue is the root path of the area, so only the exact path is the current page.
    end: true,
  }));
  return (
    <section
      aria-labelledby={titleId}
      className={cn(
        "flex flex-col gap-3 bg-surface px-[var(--gutter)] pt-[var(--panel-pad)]",
        // The tab bar draws the hairline under the strip; without tabs the strip draws its own.
        tabs.length === 0 && "border-b border-hairline pb-[var(--panel-pad)]",
      )}
    >
      <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
        {t("reports.catalogue.title")}
      </h1>
      {tabs.length === 0 ? null : <RouteTabs label={t("reports.tabs.label")} tabs={tabs} />}
    </section>
  );
}
