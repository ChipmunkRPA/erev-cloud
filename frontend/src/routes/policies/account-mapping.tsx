// SF-13:account-mapping Account mapping (SCREENS §11.6 versions grid; §0.4 RT-69; §0.7 SCR-ST-03,
// SCR-ST-05, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-19; 04 API-R-20 `GET, POST
// /account-mappings`; T-REF-14; REQ-REF-008; BUILD_SPEC RFD-25). The Policies frame and the DataGrid of
// mapping versions (name linking the editor, version, E-12 status, effective dates, rule count, author,
// approver); "New mapping version" (`config.author`) copies the published version.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { parseFilters } from "../../components/filter-bar/filters";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  type AccountMapping,
  type AccountMappingCreate,
  ACCOUNT_MAPPINGS_PATH,
  EVERY_ACCOUNT_MAPPING,
  fetchMappingsPage,
  fetchPublishedMapping,
  mappingsGridKey,
  mappingVersionRoute,
  publishedMappingKey,
} from "../../lib/api/queries/account-mappings";
import { useMe } from "../../lib/api/queries/me";
import { CONFIG_AUTHOR_PERMISSION, CONFIG_READ_PERMISSION } from "../../lib/api/queries/rule-sets";
import { placeProblem } from "../../lib/api/refusals";
import { effectiveInstant, formatNumber, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { PoliciesPageHeader } from "./revenue";

/** SCREENS §11.6 versions grid columns. */
export function mappingColumns(): readonly GridColumn<AccountMapping>[] {
  return [
    {
      id: "name",
      header: t("policies.mapping.column.mapping"),
      kind: "identifier",
      value: (mapping) => mapping.name,
      href: (mapping) => mappingVersionRoute(mapping.id),
      width: 220,
    },
    {
      id: "version",
      header: t("policies.mapping.column.version"),
      kind: "text",
      value: (mapping) => t("policies.version.number", { version: String(mapping.version_no) }),
      sortKey: "version_no",
      width: 96,
    },
    {
      id: "status",
      header: t("policies.mapping.column.status"),
      kind: "status",
      value: (mapping) => mapping.status,
      render: (mapping) => (
        <StatusChip status={chipFor("E-12", mapping.status)?.status ?? mapping.status} />
      ),
    },
    // 04 SC-V `effective_from` and `effective_to` are instants; the grid shows their UTC date (DS-FMT-17).
    {
      id: "effective_from",
      header: t("policies.mapping.column.effectiveFrom"),
      kind: "date",
      value: (mapping) =>
        mapping.effective_from === null ? null : timestampDate(mapping.effective_from),
    },
    {
      id: "effective_to",
      header: t("policies.mapping.column.effectiveTo"),
      kind: "date",
      value: (mapping) =>
        mapping.effective_to === null ? null : timestampDate(mapping.effective_to),
    },
    {
      id: "rule_count",
      header: t("policies.mapping.column.rules"),
      kind: "number",
      numberKind: "count",
      value: (mapping) => String(mapping.rule_count),
      width: 96,
    },
    {
      id: "author",
      header: t("policies.mapping.column.author"),
      kind: "text",
      value: (mapping) => mapping.created_by.display_name,
      width: 160,
    },
    {
      id: "approver",
      header: t("policies.mapping.column.approver"),
      kind: "text",
      value: (mapping) => mapping.published_by?.display_name ?? null,
      width: 160,
    },
  ];
}

export function AccountMappings() {
  const me = useMe();
  const access = useAccess();
  const title = t("policies.tabs.accountMapping");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(CONFIG_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    return <MappingList access={access} />;
  }
  return (
    <div
      data-testid="SF-13-account-mapping-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <PoliciesPageHeader />
      {body}
    </div>
  );
}

function MappingList({ access }: { readonly access: Access }) {
  const { search } = useLocation();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  const author = access.holdsAnywhere(CONFIG_AUTHOR_PERMISSION);
  const query = parseFilters(search, []).query;
  const columns = useMemo(() => mappingColumns(), []);
  const source: GridSource<AccountMapping> = {
    queryKey: mappingsGridKey(query),
    fetchPage: (cursor, sort) => fetchMappingsPage(query, cursor, sort),
  };
  const countLabel = (value: number) =>
    t("policies.mapping.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  const newVersion = author
    ? { label: t("policies.mapping.new"), onAction: () => setCreating(true) }
    : undefined;
  return (
    <div
      data-testid="SF-13-account-mapping-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <PoliciesPageHeader />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<AccountMapping>
          name="account-mappings"
          title={t("policies.mapping.grid")}
          errorTitle={t("policies.mapping.loadError")}
          countLabel={(value, formatted) =>
            t("policies.mapping.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(mapping) => mapping.id}
          rowLabel={(mapping) => `${mapping.name} v${String(mapping.version_no)}`}
          testIdPrefix="SF-13"
          rowTestKey={(mapping) => `${mapping.name}-${String(mapping.version_no)}`}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            newVersion === undefined ? undefined : (
              <Button variant="primary" onClick={newVersion.onAction}>
                {newVersion.label}
              </Button>
            )
          }
          filterBar={
            <FilterBar
              fields={[]}
              searchLabel={t("policies.mapping.search")}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-13-filter-bar-account-mappings"
            />
          }
          emptyState={
            <div data-testid="SF-13-empty-account-mappings">
              <EmptyState
                title={t("policies.mapping.empty.title")}
                description={t("policies.mapping.empty.description")}
                action={newVersion}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("policies.mapping.noResults.title")}
              description={t("policies.mapping.noResults.description")}
            />
          }
        />
      </div>
      {creating ? <NewVersionModal onClose={() => setCreating(false)} /> : null}
    </div>
  );
}

/** SCREENS §11.6 "New mapping version": copies the published version. */
// docs/dev-guide.md DG-FE-06: the fields of "New mapping version" and the members each sends. The
// version it copies is not a field: an error on `source_version_id` is the banner's.
const NEW_MAPPING_MEMBERS = { name: ["name"], effective: ["effective_from"] } as const;

function NewVersionModal({ onClose }: { readonly onClose: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const formId = useId();
  const published = useQuery({ queryKey: publishedMappingKey(), queryFn: fetchPublishedMapping });
  // What the draft copies is known once the published version is read: `undefined` is "not read
  // yet" and never "there is none", so the command is not offered before the answer.
  const source = published.data;
  const [name, setName] = useState("");
  const [effectiveText, setEffectiveText] = useState("");
  const [effective, setEffective] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<AccountMapping>({
    method: "POST",
    path: ACCOUNT_MAPPINGS_PATH,
    invalidates: [EVERY_ACCOUNT_MAPPING],
  });
  const placed = useMemo(() => placeProblem(create.problem, NEW_MAPPING_MEMBERS), [create.problem]);
  const nameError =
    placed.fields.name ??
    (attempted && name.trim() === "" ? t("policies.mapping.newDialog.nameRequired") : null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (source === undefined) {
      return;
    }
    setAttempted(true);
    if (name.trim() === "") {
      return;
    }
    const body: AccountMappingCreate = {
      name: name.trim(),
      effective_from: effective === null ? null : effectiveInstant(effective),
      source_version_id: source?.id ?? null,
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.mapping.newDialog.created", {
          name: outcome.data.name,
          version: String(outcome.data.version_no),
        }),
      });
      onClose();
      void navigate(mappingVersionRoute(outcome.data.id));
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("policies.mapping.new")}
      description={
        source === undefined
          ? published.isError
            ? undefined
            : t("policies.mapping.newDialog.loading")
          : source === null
            ? t("policies.mapping.newDialog.fromScratch")
            : t("policies.mapping.newDialog.copies", {
                name: source.name,
                version: String(source.version_no),
              })
      }
      primaryAction={{
        label: t("policies.mapping.newDialog.create"),
        form: formId,
        disabledReason: source === undefined ? t("policies.mapping.newDialog.unread") : undefined,
      }}
      submitting={create.pending}
      onClose={onClose}
      testId="SF-13-dialog-new-mapping"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        {source === undefined && published.isError ? (
          <Banner
            tone="warning"
            title={t("policies.mapping.newDialog.loadError")}
            actions={
              <Button variant="link" onClick={() => void published.refetch()}>
                {t("policies.mapping.newDialog.retry")}
              </Button>
            }
          />
        ) : null}
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="name"
          label={t("policies.mapping.newDialog.name")}
          required
          error={nameError}
          width="full"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={controlClass(nameError !== null)}
            />
          )}
        </Field>
        <Field
          name="effective_from"
          label={t("policies.mapping.newDialog.effectiveFrom")}
          optional
          error={placed.fields.effective}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={effectiveText}
              onChange={setEffectiveText}
              onValue={setEffective}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}
