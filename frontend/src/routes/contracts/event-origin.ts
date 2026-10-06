// The origin of a stream event in words (SCREENS §5.6 "Events" and §4.4 column 9, as bound rev 1.62; 04
// T-CON-05 `origin`, API-S-Event `is_manual`, `source_row`, `created_by`; BUILD_SPEC CTR-22, CTR-23).
// One rule for the two screens that show it, the Events panel of SF-03:obligation and the invoices of
// SF-03:billing: a person's entry, then the import row, then the name of the `origin` literal.
import type { components } from "../../lib/api/schema";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";

type Actor = components["schemas"]["ActorOut"];

/** The members of API-S-Event the origin is told from; both models of the schema carry them. */
export interface OriginMembers {
  readonly origin: string;
  readonly is_manual: boolean;
  readonly source_row: { readonly row_number: number } | null;
  readonly created_by: Pick<Actor, "kind" | "display_name">;
}

/**
 * "Manual" for an event a person recorded — also one applied from her submission, which is appended
 * as `SYSTEM` and stays manual —, "Import row <n>" for an event with a source row, else the name of
 * the literal: the six of 04 T-CON-05, an API client by its name where the event's principal is one.
 * A literal outside the six is printed as it is, so a seventh is seen and not hidden.
 */
export function eventOriginText(event: OriginMembers): string {
  if (event.is_manual) {
    return t("contracts.obligation.events.origin.manual");
  }
  if (event.source_row !== null) {
    return t("contracts.obligation.events.origin.importRow", {
      row: formatNumber(event.source_row.row_number, { kind: "count" }),
    });
  }
  switch (event.origin) {
    case "API":
      return event.created_by.kind === "API_CLIENT"
        ? t("contracts.obligation.events.origin.apiClient", {
            name: event.created_by.display_name,
          })
        : t("contracts.obligation.events.origin.API");
    case "UI":
    case "IMPORT":
    case "ADAPTER":
    case "SYSTEM":
    case "MIGRATION":
      return t(`contracts.obligation.events.origin.${event.origin}`);
    default:
      return event.origin;
  }
}
