// SF-13:control-rules Control rules (SCREENS §11.0 frame, §11.1 "Control rules page"; §0.3 SCR-IA-02;
// §0.4 RT-60; §0.5 SCR-URL-08, SCR-URL-10; §0.7 SCR-ST-03, SCR-ST-04; DESIGN_SYSTEM DS-CMP-10, DS-CMP-13;
// 04 API-R-25 `GET /rule-sets?kind=`; BUILD_SPEC RFD-22). One DataGrid "Control rules" of the approval
// routing, auto-approval, hold, combination detection and data-quality rule sets, with quick search and
// the filter chip "Kind" in the URL; "New rule set" (`config.author`) opens the create drawer.
import { useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridSource } from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters, withFilters } from "../../components/filter-bar/filters";
import { Button } from "../../components/ui/Button";
import {
  CONTROL_KINDS,
  fetchRuleSetsPage,
  type RuleSet,
  type RuleSetKind,
  ruleSetKindLabel,
  ruleSetsKey,
} from "../../lib/api/queries/rule-sets";
import { t } from "../../lib/i18n/t";
import { NewRuleSetDrawer, PoliciesPage, ruleSetColumns } from "./revenue";

/** SCREENS §11.1 filter chip "Kind". */
export function kindFilterField(): FilterField {
  return {
    name: "kind",
    label: t("policies.controlRules.filter.kind"),
    kind: "enum",
    operators: ["in"],
    options: CONTROL_KINDS.map((value) => ({ value, label: ruleSetKindLabel(value) })),
  };
}

/** The kinds of the URL filter chip, restricted to the control kinds; every control kind without one. */
export function selectedKinds(search: string): {
  readonly kinds: readonly RuleSetKind[];
  readonly query: string;
  readonly filtered: boolean;
} {
  const parsed = parseFilters(search, [kindFilterField()]);
  const chip = parsed.filters.find((filter) => filter.field === "kind");
  const chosen = CONTROL_KINDS.filter((kind) => chip?.values.includes(kind) === true);
  return {
    kinds: chosen.length === 0 ? CONTROL_KINDS : chosen,
    query: parsed.query,
    filtered: chosen.length > 0 || parsed.query !== "",
  };
}

export function ControlRules() {
  return <PoliciesPage>{(author) => <ControlRulesGrid author={author} />}</PoliciesPage>;
}

function ControlRulesGrid({ author }: { readonly author: boolean }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const { kinds, query, filtered } = selectedKinds(location.search);
  const source: GridSource<RuleSet> = {
    queryKey: ruleSetsKey(kinds, query),
    fetchPage: (cursor, sort) => fetchRuleSetsPage(kinds, cursor, sort, query),
  };
  const clearFilters = () => {
    void navigate(
      { pathname: location.pathname, search: withFilters(location.search, "", []) },
      { replace: true },
    );
  };

  return (
    <>
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<RuleSet>
          name="control-rules"
          title={t("policies.controlRules.title")}
          countLabel={(count, formatted) => t("policies.ruleSets.count", { count, formatted })}
          columns={ruleSetColumns()}
          source={source}
          rowKey={(set) => set.id}
          rowLabel={(set) => set.code}
          testIdPrefix="SF-13"
          rowTestKey={(set) => set.code}
          onTotalChange={(next) => setTotal(next?.count)}
          filterBar={
            <FilterBar
              fields={[kindFilterField()]}
              searchLabel={t("policies.controlRules.search")}
              resultCount={total}
              resultLabel={(count) =>
                t("policies.ruleSets.count", { count, formatted: String(count) })
              }
            />
          }
          toolbarActions={
            author ? (
              <Button variant="primary" size="sm" onClick={() => setCreating(true)}>
                {t("policies.ruleSets.new")}
              </Button>
            ) : undefined
          }
          emptyState={
            filtered ? undefined : (
              <EmptyState
                title={t("policies.controlRules.empty.title")}
                description={t("policies.controlRules.empty.description")}
              />
            )
          }
          noResults={
            <EmptyState
              title={t("policies.controlRules.noResults")}
              description=""
              action={{ label: t("policies.controlRules.clearFilters"), onAction: clearFilters }}
            />
          }
        />
      </div>
      {creating ? (
        <NewRuleSetDrawer kinds={CONTROL_KINDS} onClose={() => setCreating(false)} />
      ) : null}
    </>
  );
}
