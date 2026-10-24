import { useState } from "react";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage } from "../../lib/api/lists";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { PortfolioEvidence } from "./portfolio-evidence";

type Estimate = components["schemas"]["EstimateOut"];
type Portfolio = components["schemas"]["PortfolioOut"];
type Version = components["schemas"]["EstimateVersionOut"];
type Values = components["schemas"]["PortfolioEstimateVersionIn"];
const label = (key: string) => t(`settings.portfolioVersions.${key}`);
const KEY = queryKey("portfolios", "tenant");
const valuesOf = (v: Version | null): Values => ({
  effective_date: v?.effective_date ?? "",
  currency: v?.currency ?? "",
  rationale: v?.rationale ?? "",
  rate: v?.rate ?? null,
  expected_quantity: v?.expected_quantity ?? null,
  unconstrained_amount: v?.unconstrained_amount ?? null,
  constrained_amount: v?.constrained_amount ?? null,
  most_conservative_amount: v?.most_conservative_amount ?? null,
  expected_total_amount: v?.expected_total_amount ?? null,
  parameters: v?.parameters ?? {},
  scenarios: (v?.scenarios ?? []).map((s) => ({
    outcome: String(s.outcome ?? ""),
    amount: String(s.amount ?? ""),
    probability: s.probability == null ? null : String(s.probability),
  })),
  constraint_checklist: (v?.constraint_checklist ?? null) as Exclude<
    Values["constraint_checklist"],
    undefined
  >,
  amortization_months: v?.amortization_months ?? null,
});

export function PortfolioVersions({
  portfolio,
  estimate,
  onClose,
}: {
  readonly portfolio: Portfolio;
  readonly estimate: Estimate;
  readonly onClose: () => void;
}) {
  const access = useAccess();
  const writable = access.holdsAnywhere("estimate.create");
  const [selected, setSelected] = useState<Version | "new" | null>(null);
  const path = `/api/v1/portfolios/${portfolio.id}/estimates/${estimate.id}/versions`;
  const columns: readonly GridColumn<Version>[] = [
    {
      id: "version",
      header: label("version"),
      kind: "number",
      numberKind: "count",
      value: (v) => String(v.version_no),
      sortKey: "version_no",
    },
    { id: "status", header: label("status"), kind: "text", value: (v) => v.status },
    {
      id: "effective",
      header: label("effective_date"),
      kind: "date",
      value: (v) => v.effective_date,
    },
    { id: "currency", header: label("currency"), kind: "text", value: (v) => v.currency },
    {
      id: "actions",
      header: label("actions"),
      kind: "actions",
      value: () => null,
      render: (v) => (
        <Button size="sm" onClick={() => setSelected(v)}>
          {label("view")}
        </Button>
      ),
    },
  ];
  return (
    <section className="flex flex-col gap-3" aria-label={label("title")}>
      <h3 className="text-heading-sm">
        {estimate.element_code} — {label("title")}
      </h3>
      <p className="text-body-sm text-fg-2">{label("help")}</p>
      <Button onClick={onClose}>{label("close")}</Button>
      <DataGrid<Version>
        name="portfolio-estimate-versions"
        title={label("title")}
        columns={columns}
        countLabel={(count, formatted) =>
          t("settings.portfolioVersions.count", { count, formatted })
        }
        source={{
          queryKey: queryKey("portfolios", "tenant", {
            id: portfolio.id,
            estimate: estimate.id,
            view: "versions",
          }),
          fetchPage: (cursor, sort) => fetchListPage<Version>(path, { sort }, cursor),
        }}
        rowKey={(v) => v.id}
        rowLabel={(v) => String(v.version_no)}
        toolbarActions={
          writable ? <Button onClick={() => setSelected("new")}>{label("new")}</Button> : undefined
        }
      />
      {selected === null || selected === "new" ? null : (
        <PortfolioEvidence
          key={selected.id}
          versionId={selected.id}
          editable={writable && selected.status === "DRAFT"}
        />
      )}
      {selected === null ? null : (
        <VersionForm
          key={selected === "new" ? "new" : `${selected.id}:${selected.row_version}`}
          path={path}
          parentVersion={portfolio.row_version}
          version={selected === "new" ? null : selected}
          estimate={estimate}
          writable={writable}
          onDone={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function VersionForm({
  path,
  parentVersion,
  version,
  estimate,
  writable,
  onDone,
}: {
  readonly path: string;
  readonly parentVersion: number;
  readonly version: Version | null;
  readonly estimate: Estimate;
  readonly writable: boolean;
  readonly onDone: () => void;
}) {
  const [values, setValues] = useState<Values>(() => valuesOf(version));
  const [networkError, setNetworkError] = useState(false);
  const editable = writable && (version === null || version.status === "DRAFT");
  const command = useCommand({
    method: version ? "PUT" : "POST",
    path: version ? `${path}/${version.id}` : path,
    ifMatch: rowIfMatch(version?.row_version ?? parentVersion),
    invalidates: [KEY],
  });
  const discard = useCommand({
    method: "POST",
    path: `${path}/${version?.id ?? ""}/discard`,
    ifMatch: rowIfMatch(version?.row_version ?? 0),
    invalidates: [KEY],
  });
  const pending = command.pending || discard.pending;
  const fields = [
    "effective_date",
    "currency",
    "rate",
    "expected_quantity",
    "unconstrained_amount",
    "most_conservative_amount",
    "constrained_amount",
    "expected_total_amount",
    "rationale",
  ] as const;
  const shownFields =
    estimate.estimate_kind === "BREAKAGE" && editable
      ? fields.filter((key) => key !== "rate" && key !== "expected_quantity")
      : fields;
  const parameters = [
    "carrying_cost_per_unit",
    "recovery_cost_per_unit",
    "window_end_date",
  ] as const;
  return (
    <form
      className="flex max-w-160 flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!editable || pending) return;
        setNetworkError(false);
        void command.submit(values).then((outcome) => {
          if (outcome.kind === "succeeded") onDone();
          if (outcome.kind === "network-error") setNetworkError(true);
        });
      }}
    >
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      <RefusalBanner problem={discard.problem} conflict={discard.banner} />
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      {shownFields.map((key) => (
        <Field
          key={key}
          name={`portfolio-version-${key}`}
          label={label(key)}
          required={["effective_date", "currency", "rationale"].includes(key)}
        >
          {(control) => (
            <input
              {...control}
              className={controlClass(false)}
              readOnly={!editable}
              disabled={pending}
              value={values[key] ?? ""}
              onChange={(e) =>
                setValues((previous) => ({
                  ...previous,
                  [key]: ["effective_date", "currency", "rationale"].includes(key)
                    ? e.target.value
                    : e.target.value || null,
                }))
              }
            />
          )}
        </Field>
      ))}
      {estimate.estimate_kind === "BREAKAGE" ? (
        <Field name="portfolio-total-breakage" label={label("totalBreakage")} required>
          {(control) => (
            <input
              {...control}
              className={controlClass(false)}
              readOnly={!editable}
              disabled={pending}
              inputMode="decimal"
              value={String(values.parameters?.portfolio_total_breakage_quantity ?? "")}
              onChange={(e) =>
                setValues((previous) => ({
                  ...previous,
                  rate: null,
                  expected_quantity: null,
                  parameters: {
                    ...previous.parameters,
                    portfolio_total_breakage_quantity: e.target.value,
                  },
                }))
              }
            />
          )}
        </Field>
      ) : null}
      {estimate.estimate_kind === "RETURN_RATE"
        ? parameters.map((key) => (
            <Field key={key} name={`portfolio-version-${key}`} label={label(key)} required>
              {(control) => (
                <input
                  {...control}
                  className={controlClass(false)}
                  readOnly={!editable}
                  disabled={pending}
                  value={String(values.parameters?.[key] ?? "")}
                  onChange={(e) =>
                    setValues((previous) => ({
                      ...previous,
                      parameters: { ...previous.parameters, [key]: e.target.value },
                    }))
                  }
                />
              )}
            </Field>
          ))
        : null}
      <h4 className="text-heading-sm">{label("scenarios")}</h4>
      {(values.scenarios ?? []).map((scenario, index) => (
        <fieldset key={index} className="flex flex-col gap-2" disabled={pending}>
          <legend>
            {label("scenario")} {index + 1}
          </legend>
          {(["outcome", "amount", "probability"] as const).map((key) => (
            <Field key={key} name={`portfolio-scenario-${index}-${key}`} label={label(key)}>
              {(control) => (
                <input
                  {...control}
                  className={controlClass(false)}
                  value={scenario[key] ?? ""}
                  readOnly={!editable}
                  onChange={(e) =>
                    setValues((previous) => ({
                      ...previous,
                      scenarios: (previous.scenarios ?? []).map((s, i) =>
                        i === index
                          ? {
                              ...s,
                              [key]:
                                key === "probability" && e.target.value === ""
                                  ? null
                                  : e.target.value,
                            }
                          : s,
                      ),
                    }))
                  }
                />
              )}
            </Field>
          ))}
          {editable ? (
            <Button
              onClick={() =>
                setValues((previous) => ({
                  ...previous,
                  scenarios: (previous.scenarios ?? []).filter((_, i) => i !== index),
                }))
              }
            >
              {label("removeScenario")}
            </Button>
          ) : null}
        </fieldset>
      ))}
      {editable ? (
        <Button
          disabledReason={pending ? label("saving") : undefined}
          onClick={() =>
            setValues((previous) => ({
              ...previous,
              scenarios: [
                ...(previous.scenarios ?? []),
                { outcome: "", amount: "", probability: null },
              ],
            }))
          }
        >
          {label("addScenario")}
        </Button>
      ) : null}
      <div className="flex gap-2">
        {editable ? (
          <Button
            type="submit"
            loading={command.pending}
            disabledReason={discard.pending ? label("saving") : undefined}
          >
            {label("save")}
          </Button>
        ) : null}
        {editable && version ? (
          <Button
            variant="danger"
            loading={discard.pending}
            disabledReason={command.pending ? label("saving") : undefined}
            onClick={() => {
              setNetworkError(false);
              void discard.submit().then((outcome) => {
                if (outcome.kind === "succeeded") onDone();
                if (outcome.kind === "network-error") setNetworkError(true);
              });
            }}
          >
            {label("discard")}
          </Button>
        ) : null}
        <Button onClick={onDone} disabledReason={pending ? label("saving") : undefined}>
          {label("closeEditor")}
        </Button>
      </div>
    </form>
  );
}
