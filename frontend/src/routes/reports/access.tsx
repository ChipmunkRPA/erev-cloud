// SCR-PERM-01 for the report run register and a run record (SCREENS §0.6; §0.4 RT-106, RT-33; 04
// API-R-41 rev 1.128): the two screens open for a holder of `report.run` or `audit.read`.
import { EmptyState } from "../../components/feedback/EmptyState";
import { t } from "../../lib/i18n/t";

export function ReportRunsAccessLimited() {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("reports.runs.access.area") })}
      description={t("settings.access.description", {
        permission: t("reports.runs.access.permission"),
      })}
    />
  );
}
