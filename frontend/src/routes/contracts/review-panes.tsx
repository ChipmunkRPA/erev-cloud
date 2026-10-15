import { type ReactNode, useSyncExternalStore } from "react";

import { PanelTabs } from "../../components/record/Tabs";
import { t } from "../../lib/i18n/t";

const query = "(min-width: 1440px)";
function subscribe(onChange: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener("change", onChange);
  return () => media?.removeEventListener("change", onChange);
}
function snapshot() {
  return window.matchMedia?.(query).matches ?? true;
}

/** SF-20 keeps controlled review values in its parent across viewport changes. */
export function ReviewPanes({
  pane,
  onChange,
  document,
  fields,
}: {
  readonly pane: string;
  readonly onChange: (pane: string) => void;
  readonly document: ReactNode;
  readonly fields: ReactNode;
}) {
  const wide = useSyncExternalStore(subscribe, snapshot, () => true);
  if (wide)
    return (
      <div className="grid grid-cols-2 gap-4">
        {document}
        {fields}
      </div>
    );
  return (
    <PanelTabs
      label={t("ai.review.panes")}
      tabs={[
        { id: "document", label: t("ai.review.document") },
        { id: "fields", label: t("ai.review.fields") },
      ]}
      selectedId={pane}
      onChange={onChange}
    >
      <div hidden={pane !== "document"}>{document}</div>
      <div hidden={pane !== "fields"}>{fields}</div>
    </PanelTabs>
  );
}
