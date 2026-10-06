// SF-15:related-party-groups Related-party groups (SCREENS §9; §0.4 RT-81, §0.5 SCR-URL `drawer`, `row`,
// `q`, §0.7 SCR-ST-03, SCR-ST-05, SCR-PERM-01; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-FMT-21; 04 API-R-22
// `GET, POST /related-party-groups`, `PATCH /related-party-groups/{id}` (`If-Match`), `GET
// /customers?related_party_group_id=<id>`; T-REF-18; REQ-REF-011; BUILD_SPEC RFD-20). The Settings frame
// with the Reference data route tabs and the DataGrid "Related-party groups" (group code opening the
// drawer, name, description, members, updated). "New group" and "Edit group" (`masterdata.maintain`)
// take Code, Name and Description and list the members read-only with links to their pages.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { parseFilters } from "../../components/filter-bar/filters";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  CUSTOMER_READ_PERMISSION,
  CUSTOMER_ROUTE,
  customerRoute,
  EVERY_CUSTOMER,
  EVERY_RELATED_PARTY_GROUP,
  fetchGroupMembers,
  fetchGroupsPage,
  groupMembersKey,
  groupPath,
  groupsGridKey,
  MASTERDATA_MAINTAIN_PERMISSION,
  RELATED_PARTY_GROUPS_PATH,
  type RelatedPartyGroup,
  type RelatedPartyGroupCreate,
  type RelatedPartyGroupUpdate,
  useGroups,
} from "../../lib/api/queries/customers";
import { useMe } from "../../lib/api/queries/me";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { fieldMessages, useFieldRefusals } from "../../lib/api/refusals";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader, useBuiltPaths } from "./index";

const DRAWER_GROUP = "group";

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

/** SCREENS §9.4 groups grid columns. */
export function groupColumns(): readonly GridColumn<RelatedPartyGroup>[] {
  return [
    {
      id: "code",
      header: t("settings.relatedParty.column.group"),
      kind: "identifier",
      value: (group) => group.code,
      href: (group) => `?drawer=${DRAWER_GROUP}&row=${group.id}`,
      sortKey: "code",
      width: 160,
    },
    {
      id: "name",
      header: t("settings.relatedParty.column.name"),
      kind: "text",
      value: (group) => group.name,
      sortKey: "name",
      width: 260,
    },
    {
      id: "description",
      header: t("settings.relatedParty.column.description"),
      kind: "text",
      value: (group) => group.description,
      width: 360,
    },
    {
      id: "member_count",
      header: t("settings.relatedParty.column.members"),
      kind: "number",
      numberKind: "count",
      value: (group) => String(group.member_count),
      width: 104,
    },
    {
      id: "updated_at",
      header: t("settings.relatedParty.column.updated"),
      kind: "timestamp",
      value: (group) => group.updated_at,
      sortKey: "updated_at",
    },
  ];
}

export function RelatedPartyGroupsScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.relatedParty.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(CUSTOMER_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.contractRead"),
        })}
      />
    );
  } else {
    return <GroupsPage access={access} />;
  }
  return (
    <div
      data-testid="SF-15-related-party-groups-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference" />
      {body}
    </div>
  );
}

function GroupsPage({ access }: { readonly access: Access }) {
  const { search } = useLocation();
  const [params, setParams] = useSearchParams();
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("settings.relatedParty.title");
  const maintain = access.holdsAnywhere(MASTERDATA_MAINTAIN_PERMISSION);
  const groups = useGroups();
  const query = parseFilters(search, []).query;
  const columns = useMemo(() => groupColumns(), []);
  const source: GridSource<RelatedPartyGroup> = {
    queryKey: groupsGridKey(query),
    fetchPage: (cursor, sort) => fetchGroupsPage(query, cursor, sort),
  };
  const drawer = params.get("drawer");
  const row = params.get("row");
  const selected = row === null ? null : (groups.data?.find((group) => group.id === row) ?? null);
  const openDrawer = (id: string | null) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("drawer", DRAWER_GROUP);
        if (id === null) {
          next.delete("row");
        } else {
          next.set("row", id);
        }
        return next;
      },
      { replace: true },
    );
  };
  const closeDrawer = () => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("drawer");
        next.delete("row");
        return next;
      },
      { replace: true },
    );
  };
  const newGroup = maintain
    ? { label: t("settings.relatedParty.new"), onAction: () => openDrawer(null) }
    : undefined;
  const countLabel = (value: number) =>
    t("settings.relatedParty.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });

  return (
    <div
      data-testid="SF-15-related-party-groups-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="reference">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<RelatedPartyGroup>
          name="related-party-groups"
          title={t("settings.relatedParty.grid")}
          errorTitle={t("settings.relatedParty.loadError")}
          countLabel={(value, formatted) =>
            t("settings.relatedParty.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(group) => group.id}
          rowLabel={(group) => group.code}
          testIdPrefix="SF-15"
          rowTestKey={(group) => group.code}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            newGroup === undefined ? undefined : (
              <Button variant="primary" onClick={newGroup.onAction}>
                {newGroup.label}
              </Button>
            )
          }
          filterBar={
            <FilterBar
              fields={[]}
              searchLabel={t("settings.relatedParty.search")}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-15-filter-bar-related-party-groups"
            />
          }
          emptyState={
            <div data-testid="SF-15-empty-related-party-groups">
              <EmptyState
                title={t("settings.relatedParty.empty.title")}
                description={t("settings.relatedParty.empty.description")}
                action={newGroup}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("settings.relatedParty.noResults.title")}
              description={t("settings.relatedParty.noResults.description")}
            />
          }
        />
      </div>
      {drawer === DRAWER_GROUP && (row === null || selected !== null) ? (
        <GroupDrawer group={selected} readOnly={!maintain} onClose={closeDrawer} />
      ) : null}
    </div>
  );
}

/** The API members the fields of the group drawer send (DG-FE-06 rev 1.228). */
const GROUP_MEMBERS = { code: ["code"], name: ["name"], description: ["description"] } as const;

/** SCREENS §9.5 "New group" / "Edit group" drawer with the read-only members list. */
export function GroupDrawer({
  group,
  readOnly,
  onClose,
}: {
  /** null creates. */
  readonly group: RelatedPartyGroup | null;
  readonly readOnly: boolean;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const built = useBuiltPaths();
  const [code, setCode] = useState(group?.code ?? "");
  const [name, setName] = useState(group?.name ?? "");
  const [description, setDescription] = useState(group?.description ?? "");
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const invalidates = [EVERY_RELATED_PARTY_GROUP, EVERY_CUSTOMER];
  const create = useCommand<RelatedPartyGroup>({
    method: "POST",
    path: RELATED_PARTY_GROUPS_PATH,
    invalidates,
  });
  const edit = useCommand<RelatedPartyGroup>({
    method: "PATCH",
    path: group === null ? RELATED_PARTY_GROUPS_PATH : groupPath(group.id),
    invalidates,
  });
  const command = group === null ? create : edit;
  const refusals = useFieldRefusals(command.problem, GROUP_MEMBERS);
  const errors: Partial<Record<string, string>> = { ...fieldMessages(refusals.fields), ...local };
  const groupId = group?.id ?? "";
  const members = useQuery({
    queryKey: groupMembersKey(groupId),
    queryFn: () => fetchGroupMembers(groupId),
    enabled: groupId !== "",
  });
  const optional = (value: string) => (value.trim() === "" ? null : value.trim());
  const dirty =
    group === null
      ? code !== "" || name !== "" || description !== ""
      : code.trim() !== group.code ||
        name.trim() !== group.name ||
        optional(description) !== group.description;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (readOnly || command.pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (code.trim() === "") {
      found.code = t("settings.relatedParty.drawer.codeRequired");
    }
    if (name.trim() === "") {
      found.name = t("settings.relatedParty.drawer.nameRequired");
    }
    setLocal(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    if (group === null) {
      const body: RelatedPartyGroupCreate = {
        code: code.trim(),
        name: name.trim(),
        description: optional(description),
      };
      const outcome = await create.submit(body);
      if (outcome.kind === "succeeded" && outcome.data !== null) {
        toast.show({
          tone: "positive",
          message: t("settings.relatedParty.drawer.saved", { code: outcome.data.code }),
        });
        onClose();
      }
      return;
    }
    const patch: RelatedPartyGroupUpdate = {
      ...(code.trim() !== group.code ? { code: code.trim() } : {}),
      ...(name.trim() !== group.name ? { name: name.trim() } : {}),
      ...(optional(description) !== group.description
        ? { description: optional(description) }
        : {}),
    };
    const outcome = await edit.submit(patch, { ifMatch: rowIfMatch(group.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("settings.relatedParty.drawer.saved", { code: code.trim() }),
      });
      onClose();
    }
  };

  const problemBanner =
    command.banner !== null || refusals.banner !== null ? (
      <RefusalBanner problem={refusals.banner} placed={refusals.placed} conflict={command.banner} />
    ) : undefined;
  const customerBuilt = built.has(CUSTOMER_ROUTE);

  return (
    <Drawer
      open
      title={
        group === null
          ? t("settings.relatedParty.drawer.newTitle")
          : t("settings.relatedParty.drawer.editTitle")
      }
      subtitle={group?.name}
      dirty={dirty && !readOnly}
      submitting={command.pending}
      banner={problemBanner}
      primaryAction={
        readOnly ? undefined : { label: t("settings.relatedParty.drawer.save"), form: formId }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-15-drawer-group"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="code"
          label={t("settings.relatedParty.drawer.code")}
          required
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
                refusals.edited("code");
              }}
              className={`${controlClass(errors.code !== undefined)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="name"
          label={t("settings.relatedParty.drawer.name")}
          required
          error={errors.name ?? null}
          width="full"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              readOnly={readOnly}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                refusals.edited("name");
              }}
              className={controlClass(errors.name !== undefined)}
            />
          )}
        </Field>
        <Field
          name="description"
          label={t("settings.relatedParty.drawer.description")}
          optional
          error={errors.description ?? null}
          width="full"
        >
          {(control) => (
            <textarea
              {...control}
              readOnly={readOnly}
              rows={3}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
                refusals.edited("description");
              }}
              className={`${controlClass(errors.description !== undefined)} h-auto py-2`}
            />
          )}
        </Field>
        {group === null ? null : (
          <section
            aria-label={t("settings.relatedParty.drawer.members")}
            className="flex flex-col gap-2"
          >
            <h3 className="text-body-sm font-medium text-fg-1">
              {t("settings.relatedParty.drawer.members")}
            </h3>
            {members.isError ? (
              <Banner tone="negative" title={t("settings.relatedParty.drawer.membersLoadError")} />
            ) : members.data === undefined ? (
              <Skeleton region={t("settings.relatedParty.drawer.members")} shape="rows" count={2} />
            ) : members.data.length === 0 ? (
              <p className="text-body-sm text-fg-3">
                {t("settings.relatedParty.drawer.membersEmpty")}
              </p>
            ) : (
              <ul className="flex flex-col gap-1 text-body-sm">
                {members.data.map((member) => (
                  <li key={member.id} className="flex items-center gap-2">
                    {customerBuilt ? (
                      <Link
                        to={customerRoute(member.id)}
                        className="text-accent-fg hover:underline"
                      >
                        {member.name}
                      </Link>
                    ) : (
                      <span>{member.name}</span>
                    )}
                    {mono(member.code)}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-caption text-fg-3">
              {t("settings.relatedParty.drawer.membersNote")}
            </p>
          </section>
        )}
      </form>
    </Drawer>
  );
}
