// The dashboards of SF-08:dashboard (SCREENS_B §5.5, OQ-B-12; SCREENS RT-107): what the catalogue's
// "Dashboards" list links to (§5.1) and what the route admits. A dashboard is listed once it is built —
// a link does not go out before its target.

/** SCREENS RT-107. */
export const DASHBOARD_ROUTE = "/reports/dashboards/:dashboardCode";

export interface Dashboard {
  readonly code: string;
  /** The message key of its name, the page's `h1` lead and the catalogue link. */
  readonly nameKey: string;
  /** The message key of its one-line description in the catalogue (§5.1). */
  readonly descriptionKey: string;
}

export const DASHBOARDS: readonly Dashboard[] = [
  {
    code: "revenue",
    nameKey: "reports.dashboard.revenue.name",
    descriptionKey: "reports.dashboard.revenue.description",
  },
];

export function dashboardRoute(code: string): string {
  return `/reports/dashboards/${code}`;
}
