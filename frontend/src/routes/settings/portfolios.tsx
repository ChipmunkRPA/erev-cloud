import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage } from "../../lib/api/lists";
import { readJson, type ContractListItem } from "../../lib/api/queries/contracts";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "./index";

type Portfolio = components["schemas"]["PortfolioOut"];
type Member = components["schemas"]["PortfolioMemberOut"];
const PATH = "/api/v1/portfolios";
const KEY = queryKey("portfolios", "tenant");
const label = (key: string) => t(`settings.portfolios.${key}`);

export function PortfoliosScreen() {
  const access = useAccess();
  const [params, setParams] = useSearchParams();
  const selected = params.get("row");
  const [search, setSearch] = useState("");
  const columns: readonly GridColumn<Portfolio>[] = [
    {
      id: "code",
      header: label("code"),
      kind: "identifier",
      value: (p) => p.code,
      href: (p) => `?row=${p.id}`,
      sortKey: "code",
    },
    { id: "name", header: label("name"), kind: "text", value: (p) => p.name, sortKey: "name" },
    {
      id: "product_group",
      header: label("productGroup"),
      kind: "text",
      value: (p) => p.product_group ?? null,
    },
  ];
  return (
    <div className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={label("title")} group="reference" />
      <p className="text-body-sm text-fg-2">{label("description")}</p>
      {!access.holdsAnywhere("contract.read") ? (
        <Banner tone="warning" title={label("readRequired")} />
      ) : (
        <>
          {selected === null ? (
            <>
              <Field name="portfolio-search" label={label("search")}>
                {(control) => (
                  <input
                    {...control}
                    className={controlClass(false)}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                )}
              </Field>
              <DataGrid<Portfolio>
                countLabel={(count, formatted) =>
                  t("settings.portfolios.count", { count, formatted })
                }
                name="portfolios"
                title={label("title")}
                columns={columns}
                source={{
                  queryKey: queryKey("portfolios", "tenant", { search }),
                  fetchPage: (cursor, sort) =>
                    fetchListPage<Portfolio>(PATH, { q: search || undefined, sort }, cursor),
                }}
                rowKey={(p) => p.id}
                rowLabel={(p) => p.code}
                toolbarActions={
                  access.holdsAnywhere("estimate.create") ? (
                    <Button onClick={() => setParams({ row: "new" })}>{label("new")}</Button>
                  ) : undefined
                }
              />
            </>
          ) : (
            <>
              <Button onClick={() => setParams({})}>{label("back")}</Button>
              <PortfolioDetail
                key={selected}
                id={selected}
                onCreated={(id) => setParams({ row: id })}
              />
            </>
          )}
        </>
      )}
    </div>
  );
}

function PortfolioDetail({
  id,
  onCreated,
}: {
  readonly id: string;
  readonly onCreated: (id: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const current = useQuery({
    queryKey: queryKey("portfolios", "tenant", { id }),
    queryFn: async () => (await readJson<Portfolio>(`${PATH}/${id}`)).data,
    enabled: id !== "new",
  });
  if (id === "new") return <PortfolioForm onSaved={onCreated} />;
  if (current.isError) return <Banner tone="negative" title={current.error.message} />;
  if (current.data === undefined) return <p role="status">{label("loading")}</p>;
  return (
    <>
      <PortfolioForm
        key={`${id}:${revision}`}
        portfolio={current.data}
        onSaved={() => setRevision((value) => value + 1)}
        onReload={() => setRevision((value) => value + 1)}
      />
      <Members portfolio={current.data} />
      <EstimateDefinitions portfolio={current.data} />
    </>
  );
}

function PortfolioForm({
  portfolio,
  onSaved,
  onReload,
}: {
  readonly portfolio?: Portfolio;
  readonly onSaved: (id: string) => void;
  readonly onReload?: () => void;
}) {
  const access = useAccess();
  const writable = access.holdsAnywhere("estimate.create");
  const [version] = useState(portfolio?.row_version);
  const [code, setCode] = useState(portfolio?.code ?? "");
  const [name, setName] = useState(portfolio?.name ?? "");
  const [group, setGroup] = useState(portfolio?.product_group ?? "");
  const [description, setDescription] = useState(portfolio?.description ?? "");
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand<Portfolio>({
    method: portfolio ? "PUT" : "POST",
    path: portfolio ? `${PATH}/${portfolio.id}` : PATH,
    ...(version === undefined ? {} : { ifMatch: rowIfMatch(version) }),
    invalidates: [KEY],
  });
  return (
    <form
      className="flex max-w-120 flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!writable || command.pending || !code.trim() || !name.trim()) return;
        setNetworkError(false);
        void command
          .submit({
            code: code.trim(),
            name: name.trim(),
            product_group: group.trim() || null,
            description: description.trim() || null,
          })
          .then((outcome) => {
            if (outcome.kind === "succeeded" && outcome.data) onSaved(outcome.data.id);
            if (outcome.kind === "network-error") setNetworkError(true);
          });
      }}
    >
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {command.banner && onReload ? <Button onClick={onReload}>{label("reload")}</Button> : null}
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      {(
        [
          { key: "code", value: code, set: setCode },
          { key: "name", value: name, set: setName },
          { key: "productGroup", value: group, set: setGroup },
          { key: "descriptionField", value: description, set: setDescription },
        ] as const
      ).map((field) => (
        <Field
          key={field.key}
          name={`portfolio-${field.key}`}
          label={label(field.key)}
          required={field.key === "code" || field.key === "name"}
        >
          {(control) => (
            <input
              {...control}
              className={controlClass(false)}
              readOnly={!writable}
              disabled={command.pending}
              value={field.value}
              onChange={(e) => field.set(e.target.value)}
            />
          )}
        </Field>
      ))}
      {writable ? (
        <Button
          type="submit"
          variant="primary"
          loading={command.pending}
          disabledReason={!code.trim() || !name.trim() ? label("identityRequired") : undefined}
        >
          {label("save")}
        </Button>
      ) : null}
    </form>
  );
}

function Members({ portfolio }: { readonly portfolio: Portfolio }) {
  const access = useAccess();
  const [history, setHistory] = useState(false);
  const [remove, setRemove] = useState<Member | null>(null);
  const [adding, setAdding] = useState(false);
  const columns: readonly GridColumn<Member>[] = [
    {
      id: "contract",
      header: label("contract"),
      kind: "identifier",
      value: (m) => m.contract_external_id,
      href: (m) => `/contracts/${m.contract_id}`,
      sortKey: "contract_external_id",
    },
    {
      id: "from",
      header: label("from"),
      kind: "timestamp",
      value: (m) => m.valid_from_known_at,
      sortKey: "valid_from_known_at",
    },
    { id: "to", header: label("to"), kind: "timestamp", value: (m) => m.valid_to_known_at ?? null },
    {
      id: "actions",
      header: label("actions"),
      kind: "actions",
      value: () => null,
      render: (m) =>
        m.valid_to_known_at == null &&
        access.holds("estimate.create", { id: m.contracting_entity_id }) ? (
          <Button
            size="sm"
            onClick={() => {
              setRemove(m);
              setAdding(false);
            }}
          >
            {label("remove")}
          </Button>
        ) : null,
    },
  ];
  return (
    <section className="flex flex-col gap-3" aria-label={label("members")}>
      <h2 className="text-heading-sm">{label("members")}</h2>
      <label>
        <input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} />{" "}
        {label("history")}
      </label>
      <DataGrid<Member>
        countLabel={(count, formatted) =>
          t("settings.portfolios.memberCount", { count, formatted })
        }
        name="portfolio-members"
        title={label("members")}
        columns={columns}
        source={{
          queryKey: queryKey("portfolios", "tenant", {
            id: portfolio.id,
            history,
            view: "members",
          }),
          fetchPage: (cursor, sort) =>
            fetchListPage<Member>(
              `${PATH}/${portfolio.id}/members`,
              { include_history: history, sort },
              cursor,
            ),
        }}
        rowKey={(m) => m.id}
        rowLabel={(m) => m.contract_external_id}
        toolbarActions={
          access.holdsAnywhere("estimate.create") ? (
            <Button
              onClick={() => {
                setAdding(true);
                setRemove(null);
              }}
            >
              {label("add")}
            </Button>
          ) : undefined
        }
      />
      {adding || remove ? (
        <MembershipForm
          key={remove?.id ?? "join"}
          portfolio={portfolio}
          member={remove}
          onDone={() => {
            setAdding(false);
            setRemove(null);
          }}
        />
      ) : null}
    </section>
  );
}

function MembershipForm({
  portfolio,
  member,
  onDone,
}: {
  readonly portfolio: Portfolio;
  readonly member: Member | null;
  readonly onDone: () => void;
}) {
  const access = useAccess();
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<ContractListItem | null>(null);
  const [rationale, setRationale] = useState("");
  const [networkError, setNetworkError] = useState(false);
  const candidates = useQuery({
    queryKey: queryKey("portfolio-candidates", "tenant", { search, cursor }),
    queryFn: () =>
      fetchListPage<ContractListItem>("/api/v1/contracts", { q: search || undefined }, cursor, {
        limit: 20,
      }),
    enabled: member === null,
  });
  const command = useCommand({
    method: "POST",
    path: member
      ? `${PATH}/${portfolio.id}/members/${member.contract_id}/remove`
      : `${PATH}/${portfolio.id}/members`,
    ifMatch: rowIfMatch(portfolio.row_version),
    invalidates: [KEY],
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (command.pending || !rationale.trim() || (member === null && selected === null)) return;
        setNetworkError(false);
        void command
          .submit(
            member
              ? { rationale: rationale.trim() }
              : { contract_id: selected?.id, rationale: rationale.trim() },
          )
          .then((outcome) => {
            if (outcome.kind === "succeeded") onDone();
            if (outcome.kind === "network-error") setNetworkError(true);
          });
      }}
    >
      <h3 className="text-heading-sm">{label(member ? "remove" : "add")}</h3>
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      {member ? (
        <Link to={`/contracts/${member.contract_id}`}>{member.contract_external_id}</Link>
      ) : (
        <>
          <Field name="portfolio-contract-search" label={label("contractSearch")}>
            {(control) => (
              <input
                {...control}
                className={controlClass(false)}
                value={search}
                disabled={command.pending}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setCursor(null);
                }}
              />
            )}
          </Field>
          {candidates.isError ? <Banner tone="negative" title={candidates.error.message} /> : null}
          {candidates.isPending ? <p role="status">{label("loading")}</p> : null}
          <fieldset disabled={command.pending}>
            <legend>{label("contract")}</legend>
            {candidates.data?.items
              .filter((c) => access.holds("estimate.create", c.contracting_entity))
              .map((c) => (
                <label key={c.id} className="flex gap-2 py-1">
                  <input
                    type="radio"
                    name="portfolio-contract"
                    checked={selected?.id === c.id}
                    onChange={() => setSelected(c)}
                  />
                  {c.external_id}
                </label>
              ))}
          </fieldset>
          {candidates.data?.items.length === 0 ? <p>{label("noContracts")}</p> : null}
          <div className="flex gap-2">
            {cursor !== null ? (
              <Button onClick={() => setCursor(null)}>{label("first")}</Button>
            ) : null}
            {candidates.data?.nextCursor ? (
              <Button onClick={() => setCursor(candidates.data?.nextCursor ?? null)}>
                {label("next")}
              </Button>
            ) : null}
          </div>
          {selected ? (
            <p>
              {label("selected")}: {selected.external_id}
            </p>
          ) : null}
        </>
      )}
      <Field name="portfolio-rationale" label={label("rationale")} required>
        {(control) => (
          <textarea
            {...control}
            className={controlClass(false, true)}
            disabled={command.pending}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        )}
      </Field>
      <div className="flex gap-2">
        <Button
          type="submit"
          variant="primary"
          loading={command.pending}
          disabledReason={
            !rationale.trim() || (member === null && selected === null)
              ? label("memberRequired")
              : undefined
          }
        >
          {label("confirm")}
        </Button>
        <Button onClick={onDone} disabledReason={command.pending ? label("saving") : undefined}>
          {label("cancel")}
        </Button>
      </div>
    </form>
  );
}

function EstimateDefinitions({ portfolio }: { readonly portfolio: Portfolio }) {
  const access = useAccess();
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<"RETURN_RATE" | "BREAKAGE">("RETURN_RATE");
  const [method, setMethod] = useState<components["schemas"]["EstimateMethod"]>("RATE");
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${PATH}/${portfolio.id}/estimates`,
    ifMatch: rowIfMatch(portfolio.row_version),
    invalidates: [KEY],
  });
  type Estimate = components["schemas"]["EstimateOut"];
  const columns: readonly GridColumn<Estimate>[] = [
    {
      id: "code",
      header: label("code"),
      kind: "text",
      value: (e) => e.element_code,
      sortKey: "element_code",
    },
    {
      id: "kind",
      header: label("estimateKind"),
      kind: "text",
      value: (e) => label(`kind.${e.estimate_kind}`),
    },
    {
      id: "method",
      header: label("estimateMethod"),
      kind: "text",
      value: (e) => label(`method.${e.method}`),
    },
  ];
  return (
    <section className="flex flex-col gap-3" aria-label={label("estimates")}>
      <h2 className="text-heading-sm">{label("estimates")}</h2>
      <p className="text-body-sm text-fg-2">{label("estimateDefinitionHelp")}</p>
      <DataGrid<Estimate>
        name="portfolio-estimates"
        title={label("estimates")}
        columns={columns}
        countLabel={(count, formatted) =>
          t("settings.portfolios.estimateCount", { count, formatted })
        }
        source={{
          queryKey: queryKey("portfolios", "tenant", { id: portfolio.id, view: "estimates" }),
          fetchPage: (cursor, sort) =>
            fetchListPage<Estimate>(`${PATH}/${portfolio.id}/estimates`, { sort }, cursor),
        }}
        rowKey={(e) => e.id}
        rowLabel={(e) => e.element_code}
      />
      {access.holdsAnywhere("estimate.create") ? (
        <form
          className="flex max-w-120 flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!code.trim() || command.pending) return;
            setNetworkError(false);
            void command
              .submit({ element_code: code.trim(), estimate_kind: kind, method })
              .then((outcome) => {
                if (outcome.kind === "succeeded") setCode("");
                if (outcome.kind === "network-error") setNetworkError(true);
              });
          }}
        >
          <RefusalBanner problem={command.problem} conflict={command.banner} />
          {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
          <Field name="portfolio-estimate-code" label={label("estimateCode")} required>
            {(control) => (
              <input
                {...control}
                className={controlClass(false)}
                value={code}
                disabled={command.pending}
                onChange={(e) => setCode(e.target.value)}
              />
            )}
          </Field>
          <Field name="portfolio-estimate-kind" label={label("estimateKind")} required>
            {(control) => (
              <Select
                control={control}
                options={(["RETURN_RATE", "BREAKAGE"] as const).map((value) => ({
                  value,
                  label: label(`kind.${value}`),
                }))}
                value={kind}
                onChange={setKind}
                disabled={command.pending}
              />
            )}
          </Field>
          <Field name="portfolio-estimate-method" label={label("estimateMethod")} required>
            {(control) => (
              <Select
                control={control}
                options={(
                  [
                    "RATE",
                    "EXPECTED_VALUE",
                    "MOST_LIKELY_AMOUNT",
                    "ENTERED_AMOUNT",
                    "COST_BUILDUP",
                  ] as const
                ).map((value) => ({ value, label: label(`method.${value}`) }))}
                value={method}
                onChange={setMethod}
                disabled={command.pending}
              />
            )}
          </Field>
          <Button
            type="submit"
            loading={command.pending}
            disabledReason={code.trim() ? undefined : label("estimateCodeRequired")}
          >
            {label("createEstimate")}
          </Button>
        </form>
      ) : null}
    </section>
  );
}
