import { useState } from "react";
import { Link } from "react-router";

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
import { PortfolioAllocation } from "./portfolio-allocation";
import { PortfolioImpact } from "./portfolio-impact";
import { PortfolioEvidence } from "./portfolio-evidence";

type Estimate = components["schemas"]["EstimateOut"];
type Portfolio = components["schemas"]["PortfolioOut"];
type Version = components["schemas"]["EstimateVersionOut"];
type Values = components["schemas"]["PortfolioEstimateVersionIn"];
const label = (key: string) => t(`settings.portfolioVersions.${key}`);
const KEY = queryKey("portfolios", "tenant");
const valuesOf = (v: Version | null): Values => ({
  effective_date: v?.effective_date ?? "",
  target_obligation_keys: v?.portfolio_application_basis?.target_obligation_keys ?? null,
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
      {selected && selected !== "new" && estimate.estimate_kind === "BREAKAGE" ? (
        <PortfolioAllocation
          key={`${selected.id}:${selected.row_version}:${portfolio.row_version}`}
          path={`${path}/${selected.id}/allocation-preview`}
          revision={`${selected.row_version}:${portfolio.row_version}`}
          version={selected}
          editable={writable && selected.status === "DRAFT"}
          onRetained={setSelected}
        />
      ) : null}
      {selected &&
      selected !== "new" &&
      ["RETURN_RATE", "BREAKAGE"].includes(estimate.estimate_kind) &&
      ["DRAFT", "SUBMITTED"].includes(selected.status) ? (
        <PortfolioImpact
          key={`${selected.id}:${selected.row_version}:${portfolio.row_version}`}
          path={`${path}/${selected.id}/impact-preview`}
          revision={`${selected.row_version}:${portfolio.row_version}`}
        />
      ) : null}
      {selected && selected !== "new" && selected.portfolio_application_basis ? (
        <section aria-label={label("bindings")} className="flex flex-col gap-2">
          <h4 className="text-heading-sm">{label("bindings")}</h4>
          <p className="text-body-sm text-fg-2">{label("bindingsHelp")}</p>
          <ul>
            {selected.portfolio_application_basis.members.map((member) => (
              <li key={member.contract_id}>
                {member.contract_key}: {member.obligation_keys.join(", ")}
              </li>
            ))}
          </ul>
          {(selected.portfolio_application_basis.retired_targets ?? []).length > 0 ? (
            <>
              <h4 className="text-heading-sm">{label("retiredTargets")}</h4>
              <ul>
                {selected.portfolio_application_basis.retired_targets?.map((member) => (
                  <li key={member.contract_id}>
                    {member.contract_key}: {member.obligation_keys.join(", ")}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {(selected.portfolio_application_basis.retired_members ?? []).length > 0 ? (
            <>
              <h4 className="text-heading-sm">{label("retiredBindings")}</h4>
              <p className="text-body-sm text-fg-2">{label("retiredBindingsHelp")}</p>
              <ul>
                {selected.portfolio_application_basis.retired_members?.map((member) => (
                  <li key={member.contract_id}>
                    {member.contract_key}: {member.obligation_keys.join(", ")}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}
      {selected &&
      selected !== "new" &&
      (selected.portfolio_application_basis?.cost_conversions ?? []).length > 0 ? (
        <section aria-label={label("costFx")} className="flex flex-col gap-2">
          <h4 className="text-heading-sm">{label("costFx")}</h4>
          <p className="text-body-sm text-fg-2">{label("costFxHelp")}</p>
          {selected.portfolio_application_basis?.cost_conversions?.map((conversion) => (
            <div key={conversion.target_currency} className="flex flex-col gap-1">
              <p>
                {conversion.source_currency} → {conversion.target_currency}: {conversion.rate} (
                {conversion.rate_date})
              </p>
              <p>
                {conversion.rate_version_key} · {conversion.rate_key}
              </p>
              {(["carrying_cost_per_unit", "recovery_cost_per_unit"] as const).map((key) => (
                <p key={key}>
                  {label(key)}: {conversion.original_costs[key]} {conversion.source_currency} →{" "}
                  {conversion.converted_costs[key]} {conversion.target_currency}
                </p>
              ))}
            </div>
          ))}
        </section>
      ) : null}
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
  const submit = useCommand({
    method: "POST",
    path: `${path}/${version?.id ?? ""}/submit`,
    ifMatch: rowIfMatch(version?.row_version ?? 0),
    invalidates: [KEY],
  });
  const withdraw = useCommand({
    method: "POST",
    path: `${path}/${version?.id ?? ""}/withdraw`,
    ifMatch: rowIfMatch(version?.row_version ?? 0),
    invalidates: [KEY],
  });
  const dirty = JSON.stringify(values) !== JSON.stringify(valuesOf(version));
  const pending = command.pending || discard.pending || submit.pending || withdraw.pending;
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
      <RefusalBanner problem={submit.problem} conflict={submit.banner} />
      <RefusalBanner problem={withdraw.problem} conflict={withdraw.banner} />
      {version?.approval_request_id ? (
        <Link to={`/approvals/requests/${version.approval_request_id}`}>{label("approval")}</Link>
      ) : null}
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      {["RETURN_RATE", "BREAKAGE"].includes(estimate.estimate_kind) ? (
        <Field
          name="portfolio-version-targets"
          label={label("targetKeys")}
          help={label(
            estimate.estimate_kind === "BREAKAGE" ? "breakageTargetKeysHelp" : "targetKeysHelp",
          )}
        >
          {(control) => (
            <textarea
              {...control}
              className={controlClass(false)}
              readOnly={!editable}
              disabled={pending}
              value={(values.target_obligation_keys ?? []).join("\n")}
              onChange={(event) =>
                setValues((previous) => ({
                  ...previous,
                  target_obligation_keys: event.target.value.trim()
                    ? event.target.value
                        .split(/\n/)
                        .map((key) => key.trim())
                        .filter(Boolean)
                    : null,
                }))
              }
            />
          )}
        </Field>
      ) : null}
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
        {editable && version && ["RETURN_RATE", "BREAKAGE"].includes(estimate.estimate_kind) ? (
          <Button
            loading={submit.pending}
            disabledReason={
              pending ? label("saving") : dirty ? label("saveBeforeSubmit") : undefined
            }
            onClick={() => {
              setNetworkError(false);
              void submit.submit({}).then((outcome) => {
                if (outcome.kind === "succeeded") onDone();
                if (outcome.kind === "network-error") setNetworkError(true);
              });
            }}
          >
            {label("submit")}
          </Button>
        ) : null}
        {writable &&
        version?.status === "SUBMITTED" &&
        ["RETURN_RATE", "BREAKAGE"].includes(estimate.estimate_kind) ? (
          <Button
            loading={withdraw.pending}
            disabledReason={pending ? label("saving") : undefined}
            onClick={() => {
              setNetworkError(false);
              void withdraw.submit({}).then((outcome) => {
                if (outcome.kind === "succeeded") onDone();
                if (outcome.kind === "network-error") setNetworkError(true);
              });
            }}
          >
            {label("withdraw")}
          </Button>
        ) : null}
        <Button onClick={onDone} disabledReason={pending ? label("saving") : undefined}>
          {label("closeEditor")}
        </Button>
      </div>
    </form>
  );
}
