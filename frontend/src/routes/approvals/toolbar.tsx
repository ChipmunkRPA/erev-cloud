// SF-12 inbox toolbar (SCREENS §15.3 FilterBar, §15.5 "Select for bulk approval"; §0.5 SCR-URL-10,
// SCR-URL-18; DESIGN_SYSTEM DS-CMP-13; 04 API-R-09; BUILD_SPEC WEB-16). The chips Type, Entity and, on
// All requests, Status write `f.type`, `f.entity` and `f.status` and reach `GET /approvals` as
// `subject_type` (one), `entity` (the codes of entities in the member's scope, repeated) and `status`
// (one): the filters API-R-09 admits. The route has no search, so the bar holds chips only. The context
// pill's entity is not applied: a request without an entity (a role change, a configuration version, an
// import commit) matches no entity, and the inbox hides nothing until the member filters. On Waiting for
// me, "Select for bulk approval" writes `layout=bulk` and "Exit bulk selection" removes it.
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router";

import { FilterBar } from "../../components/filter-bar/FilterBar";
import { FILTER_PREFIX, type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { Button } from "../../components/ui/Button";
import {
  type ApprovalListFilters,
  type ApprovalStatus,
  type ApprovalSubjectType,
  type ApprovalView,
  SUBJECT_TYPES,
  VIEW_ROUTES,
} from "../../lib/api/queries/approvals";
import { useAllEntities } from "../../lib/api/queries/entities";
import { useAccess } from "../../lib/access";
import { useMe } from "../../lib/api/queries/me";
import { type Entity, STRUCTURE_READ_PERMISSION } from "../../lib/api/queries/tenant";
import { t } from "../../lib/i18n/t";
import { rawParams, withParams } from "../../lib/url/params";
import { urlChipValues } from "../contracts/list";

/** SCREENS §0.5 SCR-URL-18: the layout literal of Waiting for me in bulk selection. */
export const LAYOUT_PARAM = "layout";
export const BULK_LAYOUT = "bulk";

/** 04 E-05 literals in order, the options of the Status chip. */
export const APPROVAL_STATUSES: readonly ApprovalStatus[] = [
  "PENDING",
  "APPROVED",
  "REJECTED",
  "VOIDED",
  "WITHDRAWN",
];

/**
 * SCREENS §15.3 FilterBar: Type and Entity on every view, Status on All requests. While the entities
 * load, the chip's own values stand in as options, so a link's chip is not dropped under SCR-URL-21;
 * a member who cannot read the workspace structure has no Entity chip.
 */
export function approvalFilterFields(
  view: ApprovalView,
  search: string,
  entities: readonly Entity[] | undefined | null,
): readonly FilterField[] {
  const fields: FilterField[] = [
    {
      name: "type",
      label: t("approvals.filter.type"),
      kind: "enum",
      operators: ["is"],
      options: SUBJECT_TYPES.map((type) => ({
        value: type,
        label: t(`approvals.subjectType.${type}`),
      })),
    },
  ];
  if (entities !== null) {
    fields.push({
      name: "entity",
      label: t("approvals.filter.entity"),
      kind: "enum",
      operators: ["is", "in"],
      options:
        entities === undefined
          ? urlChipValues(search, "entity").map((value) => ({ value, label: value }))
          : entities.map((entity) => ({ value: entity.code, label: entity.code })),
      optionsLoading: entities === undefined,
    });
  }
  if (view === "all") {
    fields.push({
      name: "status",
      label: t("approvals.filter.status"),
      kind: "enum",
      operators: ["is"],
      options: APPROVAL_STATUSES.map((status) => ({
        value: status,
        label: t(`approvals.filter.statusOption.${status}`),
      })),
    });
  }
  return fields;
}

/** The API filters of the chips in `search` (04 API-R-09). */
export function approvalListFilters(
  search: string,
  fields: readonly FilterField[],
): ApprovalListFilters {
  const parsed = parseFilters(search, fields);
  const values = (name: string) =>
    parsed.filters.find((filter) => filter.field === name)?.values ?? [];
  const type: string | undefined = values("type")[0];
  const status: string | undefined = values("status")[0];
  return {
    subjectType:
      SUBJECT_TYPES.find((candidate): candidate is ApprovalSubjectType => candidate === type) ??
      null,
    entity: values("entity"),
    status:
      APPROVAL_STATUSES.find((candidate): candidate is ApprovalStatus => candidate === status) ??
      null,
  };
}

/** `to` with the filter chips of `search` appended: a request opened from a filtered view keeps them. */
export function withChips(to: string, search: string): string {
  const chips = rawParams(search)
    .filter((param) => param.name.startsWith(FILTER_PREFIX))
    .map((param) => param.raw);
  if (chips.length === 0) {
    return to;
  }
  return `${to}${to.includes("?") ? "&" : "?"}${chips.join("&")}`;
}

/** True on Waiting for me in the bulk layout (SCR-URL-18 `layout=bulk`). */
export function isBulkLayout(view: ApprovalView, search: string): boolean {
  return (
    view === "waiting" &&
    rawParams(search).some((param) => param.name === LAYOUT_PARAM && param.value === BULK_LAYOUT)
  );
}

export interface ApprovalToolbarState {
  readonly fields: readonly FilterField[];
  readonly filters: ApprovalListFilters;
  readonly bulk: boolean;
}

/** The chips of the view on screen, their API filters and whether the bulk layout is on. */
export function useApprovalToolbar(view: ApprovalView): ApprovalToolbarState {
  const { search } = useLocation();
  const me = useMe();
  const structure = useAccess().holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const entities = useAllEntities(structure);
  const options = me.data === undefined || structure ? entities.data : null;
  const fields = useMemo(
    () => approvalFilterFields(view, search, options),
    [view, search, options],
  );
  const filters = useMemo(() => approvalListFilters(search, fields), [search, fields]);
  return { fields, filters, bulk: isBulkLayout(view, search) };
}

export interface ApprovalsToolbarProps {
  readonly view: ApprovalView;
  readonly state: ApprovalToolbarState;
  /** Waiting for me, for a member who holds an approval permission: the bulk switch renders. */
  readonly bulkOffered: boolean;
}

export function ApprovalsToolbar({ view, state, bulkOffered }: ApprovalsToolbarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toggleBulk = () => {
    // The list route of the view, with its chips: a request open in the detail pane closes.
    const base = withChips(VIEW_ROUTES[view], location.search);
    const query = base.includes("?") ? base.slice(base.indexOf("?")) : "";
    const next = withParams(query, { [LAYOUT_PARAM]: state.bulk ? null : BULK_LAYOUT });
    void navigate(`${VIEW_ROUTES[view]}${next}`);
  };
  return (
    <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
      <div className="min-w-0 flex-1">
        <FilterBar fields={state.fields} testId="SF-12-filter-bar" />
      </div>
      {bulkOffered ? (
        <Button variant="secondary" onClick={toggleBulk}>
          {t(state.bulk ? "approvals.bulk.exit" : "approvals.selectBulk")}
        </Button>
      ) : null}
    </div>
  );
}
