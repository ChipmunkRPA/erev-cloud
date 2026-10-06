// SF-15:setup Workspace setup (SCREENS_B §11.1; SCREENS §0.4 RT-74, SCR-PERM-01; PRD BR-PLT-01,
// BR-PLT-02; 04 API-R-17 `GET /tenant`, `GET /entities`; API-R-18 `GET /periods`; API-R-08 `GET /users`,
// `GET /roles`, `GET /role-assignments`; DESIGN_SYSTEM DS-CMP-10 static table, DS-CMP-19, DS-CMP-29;
// BUILD_SPEC RFD-19, BS3-D-08). The first-run checklist of a workspace: items 1 to 3 pass from live data
// (an entity; an open period; `contract.create` and `contract.approve` held by different people), items
// 4 to 6 are optional and carry no status, and item links render only for built routes (XR-14). Once
// `setup_completed_at` is set a positive banner shows and the checklist stays visible, read-only. The
// "Setup grants" table lists the role assignments rule AUTO-BOOTSTRAP approved.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";
import { Link } from "react-router";

import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Button } from "../../components/ui/Button";
import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { fetchListPage } from "../../lib/api/lists";
import { useMe } from "../../lib/api/queries/me";
import {
  ENTITIES_PATH,
  fetchCounted,
  fetchPeriods,
  periodLabel,
  periodsKey,
  useTenant,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SETUP_PERMISSION, SettingsPageHeader, useBuiltPaths } from "./index";

type User = components["schemas"]["UserOut"];
type Role = components["schemas"]["RoleOut"];
type RoleAssignment = components["schemas"]["RoleAssignmentOut"];

export const USERS_PATH = "/api/v1/users";
export const ROLES_PATH = "/api/v1/roles";
export const ROLE_ASSIGNMENTS_PATH = "/api/v1/role-assignments";
/** PRD BR-PLT-02: the permissions to prepare and to approve contracts. */
export const PREPARE_PERMISSION = "contract.create";
export const APPROVE_PERMISSION = "contract.approve";
/** 04 §14.3 rule set and rule key of the setup grants. */
export const AUTO_BOOTSTRAP = "AUTO-BOOTSTRAP";
/** 04 API-R-08 reads of item 3 and the setup grants. */
const USERS_PERMISSION = "user.manage";
const ROLES_PERMISSION = "role.manage";

export type SetupStatus = "Passed" | "In progress" | "Not started";

/**
 * Item 3 progress: 2 when some ACTIVE member holding `contract.create` differs from some ACTIVE member
 * holding `contract.approve`; 1 when either permission is held; else 0.
 */
export function heldByDifferentPeople(users: readonly User[], roles: readonly Role[]): number {
  const permissionsOf = new Map(
    roles.filter((candidate) => candidate.is_active).map((candidate) => [candidate.id, candidate]),
  );
  const holders = (permission: string) =>
    users
      .filter(
        (user) =>
          user.status === "ACTIVE" &&
          user.roles.some(
            (grant) =>
              grant.status === "ACTIVE" &&
              // eslint-disable-next-line no-restricted-syntax -- a role's permissions, not the member's (DG-FE-16)
              permissionsOf.get(grant.role.id)?.permissions.includes(permission) === true,
          ),
      )
      .map((user) => user.id);
  const preparers = holders(PREPARE_PERMISSION);
  const approvers = holders(APPROVE_PERMISSION);
  if (preparers.some((preparer) => approvers.some((approver) => approver !== preparer))) {
    return 2;
  }
  return preparers.length > 0 || approvers.length > 0 ? 1 : 0;
}

export function progressStatus(held: number, needed: number): SetupStatus {
  if (held >= needed) {
    return "Passed";
  }
  return held > 0 ? "In progress" : "Not started";
}

interface ChecklistItem {
  readonly n: number;
  readonly status: SetupStatus | null;
  readonly detail: string | null;
  /** SCREENS §0.4 route of the item's link. */
  readonly path: string;
}

async function fetchAll<T>(
  path: string,
  query: Record<string, string> = {},
): Promise<readonly T[]> {
  const page = await fetchListPage<T>(path, query, null, { limit: 200, count: false });
  return page.items;
}

export function WorkspaceSetup() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.setup.title");
  // The checklist reads `GET /tenant`, which answers a holder for all entities alone.
  const allowed = access.holdsForAll(SETUP_PERMISSION);

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("settings.setup.checklist")} shape="rows" count={6} />;
  } else if (!allowed) {
    body = (
      <AccessLimited
        area={title}
        permissions={[SETUP_PERMISSION]}
        allEntities={
          access.holdsAnywhere(SETUP_PERMISSION)
            ? { message: "settings.setup.access.allEntities", permission: SETUP_PERMISSION }
            : undefined
        }
      />
    );
  } else {
    body = <SetupSections access={access} />;
  }

  return (
    <div
      data-testid="SF-15-setup-page"
      className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

function SetupSections({ access }: { readonly access: Access }) {
  const built = useBuiltPaths();
  const tenant = useTenant();
  const entities = useQuery({
    queryKey: queryKey("entities", "tenant", { count: true }),
    queryFn: () => fetchCounted<unknown>(ENTITIES_PATH, {}),
  });
  const openPeriods = useQuery({
    queryKey: periodsKey({ state: "open", view: "setup" }),
    // SCREENS_B §11.1: `GET /periods?state=open&limit=1`, the earliest open period.
    queryFn: () => fetchPeriods({ state: "open" }, 1),
  });
  const people = useQuery({
    queryKey: queryKey("users", "tenant", { view: "setup" }),
    queryFn: async () => {
      const [users, roles] = await Promise.all([
        fetchAll<User>(USERS_PATH, { status: "ACTIVE" }),
        fetchAll<Role>(ROLES_PATH),
      ]);
      return heldByDifferentPeople(users, roles);
    },
    enabled: access.holdsAnywhere(USERS_PERMISSION) && access.holdsAnywhere(ROLES_PERMISSION),
  });
  const grants = useQuery({
    queryKey: queryKey("role-assignments", "tenant", { view: "setup-grants" }),
    queryFn: () => fetchAll<RoleAssignment>(ROLE_ASSIGNMENTS_PATH),
    enabled: access.holdsAnywhere(ROLES_PERMISSION),
  });
  const checklistId = useId();
  const grantsId = useId();

  const failed = [tenant, entities, openPeriods, people, grants].find((query) => query.isError);
  if (failed?.error !== undefined && failed.error !== null) {
    return (
      <Banner
        tone="negative"
        title={t("settings.setup.loadError")}
        actions={
          <Button
            variant="link"
            onClick={() => {
              for (const query of [tenant, entities, openPeriods, people, grants]) {
                if (query.isError) {
                  void query.refetch();
                }
              }
            }}
          >
            {t("settings.setup.retry")}
          </Button>
        }
      >
        {failed.error.message}
      </Banner>
    );
  }
  if (
    tenant.data === undefined ||
    entities.data === undefined ||
    openPeriods.data === undefined ||
    (people.isEnabled && people.data === undefined)
  ) {
    return <Skeleton region={t("settings.setup.checklist")} shape="rows" count={6} />;
  }

  const entityCount = entities.data.total?.count ?? entities.data.items.length;
  const firstOpen = openPeriods.data[0];
  const held = people.data;
  const items: readonly ChecklistItem[] = [
    {
      n: 1,
      status: entityCount > 0 ? "Passed" : "Not started",
      detail:
        entityCount > 0
          ? t("settings.setup.items.1.detail", { count: entityCount })
          : t("settings.setup.items.1.none"),
      path: "/settings/entities",
    },
    {
      n: 2,
      status: firstOpen === undefined ? "Not started" : "Passed",
      detail:
        firstOpen === undefined
          ? t("settings.setup.items.2.none")
          : t("settings.setup.items.2.detail", { period: periodLabel(firstOpen.period) }),
      path: "/settings/calendars",
    },
    {
      n: 3,
      status: held === undefined ? null : progressStatus(held, 2),
      detail: held === undefined ? null : t("settings.setup.items.3.detail", { held }),
      path: "/settings/users",
    },
    { n: 4, status: null, detail: null, path: "/policies/accounting" },
    { n: 5, status: null, detail: null, path: "/data/integrations" },
    { n: 6, status: null, detail: null, path: "/data/templates" },
  ];
  const complete = tenant.data.setup_completed_at !== null;
  const setupGrants = (grants.data ?? []).filter((grant) => grant.setup_grant);
  const header = "px-3 py-2 text-start font-medium text-fg-2";
  const cell = "px-3 py-3 align-top";

  return (
    <>
      {complete ? (
        <div data-testid="SF-15-banner-setup-complete">
          <Banner tone="positive" title={t("settings.setup.complete")} />
        </div>
      ) : null}
      <section aria-labelledby={checklistId} className="flex flex-col gap-2">
        <h2 id={checklistId} className="text-title-sm text-fg-1">
          {t("settings.setup.heading", { workspace: tenant.data.display_name })}
        </h2>
        <p className="text-body-sm text-fg-2">{t("settings.setup.description")}</p>
        <table
          aria-label={t("settings.setup.checklist")}
          data-testid="SF-15-grid-setup"
          className="w-full border-collapse text-body-sm"
        >
          <thead className="sr-only">
            <tr>
              <th scope="col">{t("settings.setup.column.step")}</th>
              <th scope="col">{t("settings.setup.column.progress")}</th>
              <th scope="col">{t("settings.setup.column.next")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const label = t(`settings.setup.items.${String(item.n)}.label`);
              return (
                <tr
                  key={item.n}
                  data-testid={`SF-15-row-setup-${String(item.n)}`}
                  className="border-b border-hairline"
                >
                  <th scope="row" className={`${cell} text-start font-normal`}>
                    <span className="flex flex-wrap items-center gap-3">
                      <span className="w-24 shrink-0">
                        {item.status === null ? (
                          item.n > 3 ? (
                            <OutlineChip label={t("settings.setup.optional")} />
                          ) : null
                        ) : (
                          <StatusChip status={item.status} />
                        )}
                      </span>
                      <span className="num w-4 shrink-0 text-fg-3">{item.n}</span>
                      <span className="font-medium text-fg-1">{label}</span>
                    </span>
                  </th>
                  <td className={`${cell} text-fg-2`}>{item.detail}</td>
                  <td className={`${cell} text-end`}>
                    {built.has(item.path) ? (
                      <Link to={item.path} className="text-accent-fg hover:underline">
                        {t(`settings.setup.items.${String(item.n)}.link`)}
                      </Link>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section aria-labelledby={grantsId} className="flex flex-col gap-2">
        <h2 id={grantsId} className="text-title-sm text-fg-1">
          {t("settings.setup.grants.title")}
        </h2>
        <p className="text-body-sm text-fg-2">{t("settings.setup.grants.description")}</p>
        <table
          aria-label={t("settings.setup.grants.title")}
          data-testid="SF-15-grid-setup-grants"
          className="w-full border-collapse text-body-sm"
        >
          <thead>
            <tr className="border-b border-default bg-subtle">
              <th scope="col" className={header}>
                {t("settings.setup.grants.column.member")}
              </th>
              <th scope="col" className={header}>
                {t("settings.setup.grants.column.role")}
              </th>
              <th scope="col" className={header}>
                {t("settings.setup.grants.column.scope")}
              </th>
              <th scope="col" className={header}>
                {t("settings.setup.grants.column.granted")}
              </th>
              <th scope="col" className={header}>
                {t("settings.setup.grants.column.rule")}
              </th>
            </tr>
          </thead>
          <tbody>
            {setupGrants.length === 0 ? (
              <tr className="border-b border-hairline">
                <td colSpan={5} className={`${cell} text-fg-2`}>
                  {grants.isEnabled ? t("settings.setup.grants.empty") : null}
                </td>
              </tr>
            ) : (
              setupGrants.map((grant) => (
                <tr key={grant.id} className="border-b border-hairline">
                  <th scope="row" className={`${cell} text-start font-medium text-fg-1`}>
                    {grant.member_name}
                  </th>
                  <td className={cell}>{grant.role.name}</td>
                  <td className={cell}>
                    {grant.is_all_entities
                      ? t("settings.setup.grants.allEntities")
                      : grant.entities.map((candidate) => candidate.code).join(", ")}
                  </td>
                  <td className={`${cell} num`}>{formatTimestamp(grant.valid_from)}</td>
                  <td className={`${cell} font-mono`}>{AUTO_BOOTSTRAP}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}
