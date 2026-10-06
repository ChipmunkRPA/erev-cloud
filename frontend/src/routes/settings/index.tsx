// SF-15 Settings index (SCREENS_B §9.1; SCREENS §0.3 SCR-IA-03, §0.4 RT-71 to RT-93 and RT-110;
// DESIGN_SYSTEM DS-AP-02, DS-CMP-07, DS-CMP-10, DS-CMP-29; 04 API-R-03 `GET /me`, API-R-17 `GET /tenant`;
// 03 REQ-UX-001). One start-aligned index of the settings pages: one `section` with an `h2` per group
// and a static table of links with descriptions, never a card grid. A link renders only when the user
// holds a read permission of its page (any-of, SCR-PERM-01) and its route is built (XR-14); a group
// without a link is not rendered. A `settings.manage` holder whose workspace has no `setup_completed_at`
// sees the banner "Workspace setup is not complete.", whose "Finish setup" link renders once SF-15:setup
// is built. `SettingsPageHeader` gives each settings page the breadcrumb "Settings /", its `h1` and the
// route tab bar of its group.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";
import { Link, useMatches } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { type Access, useAccess } from "../../lib/access";
import { api, unwrap } from "../../lib/api/client";
import { useMe } from "../../lib/api/queries/me";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { testIdKey } from "../onboarding/select-workspace";

export type Tenant = components["schemas"]["TenantOut"];

/** SCREENS RT-71. */
export const SETTINGS_PATH = "/settings";
/** SCREENS RT-74 SF-15:setup. */
export const SETUP_PATH = "/settings/setup";
/** 04 API-R-17: `GET /tenant` and the setup banner need `settings.manage`. */
export const SETUP_PERMISSION = "settings.manage";

export type SettingsGroupId =
  "preferences" | "workspace" | "reference" | "access" | "developer" | "ai" | "sandbox";

export interface SettingsPage {
  /** The screen id (SCREENS §0.4). */
  readonly screen: string;
  readonly path: string;
  /** The message key under `settings.index.pages`. */
  readonly key: string;
  /** Any-of read permissions (SCR-PERM-01); empty for every authenticated member. */
  readonly permissions: readonly string[];
  /**
   * Those of `permissions` under which the page is the workspace's, one for all entities: its read
   * answers a holder for all entities alone (SCREENS §0.6 SCR-PERM-02 (c)), so its link asks that.
   */
  readonly workspaceWide: readonly string[];
  /** SCREENS_B §9.1 gives the page a description. */
  readonly described: boolean;
}

export interface SettingsGroup {
  readonly id: SettingsGroupId;
  readonly pages: readonly SettingsPage[];
}

function settingsPage(
  screen: string,
  path: string,
  key: string,
  permissions: readonly string[],
  described = false,
  workspaceWide: readonly string[] = [],
): SettingsPage {
  return { screen, path, key, permissions, described, workspaceWide };
}

/** A page of the whole workspace: every read permission of it is asked for all entities. */
function workspacePage(
  screen: string,
  path: string,
  key: string,
  permissions: readonly string[],
  described = false,
): SettingsPage {
  return settingsPage(screen, path, key, permissions, described, permissions);
}

/** SCREENS_B §9.1 groups and pages in wireframe order, with the SCREENS §0.4 read permissions. */
export const SETTINGS_GROUPS: readonly SettingsGroup[] = [
  {
    id: "preferences",
    pages: [
      settingsPage("SF-15:notifications", "/settings/notifications", "notifications", [], true),
      settingsPage("SF-15:profile", "/settings/profile", "profile", [], true),
    ],
  },
  {
    id: "workspace",
    pages: [
      workspacePage("SF-15:setup", SETUP_PATH, "setup", ["settings.manage"], true),
      settingsPage("SF-15:entities", "/settings/entities", "entities", ["config.read"], true),
      settingsPage("SF-15:calendars", "/settings/calendars", "calendars", ["config.read"], true),
      settingsPage("SF-15:currencies", "/settings/currencies", "currencies", ["config.read"], true),
      settingsPage(
        "SF-15:chart-of-accounts",
        "/settings/chart-of-accounts",
        "chartOfAccounts",
        ["config.read"],
        true,
      ),
      workspacePage(
        "SF-15:workspace",
        "/settings/workspace",
        "workspace",
        ["settings.manage"],
        true,
      ),
    ],
  },
  {
    id: "reference",
    pages: [
      settingsPage("SF-15:customers", "/settings/customers", "customers", ["contract.read"]),
      settingsPage(
        "SF-15:related-party-groups",
        "/settings/related-party-groups",
        "relatedPartyGroups",
        ["contract.read"],
      ),
      settingsPage("SF-15:products", "/settings/products", "products", ["contract.read"]),
    ],
  },
  {
    id: "access",
    pages: [
      settingsPage("SF-14", "/settings/users", "users", ["user.manage"]),
      settingsPage("SF-14:roles", "/settings/roles", "roles", ["role.manage"]),
      settingsPage("SF-14:sod", "/settings/separation-of-duties", "sod", ["role.manage"]),
      workspacePage("SF-14:access-reviews", "/settings/access-reviews", "accessReviews", [
        "access.approve",
      ]),
      workspacePage("SF-14:security", "/settings/security", "security", ["settings.manage"]),
      workspacePage("SF-14:support-access", "/settings/support-access", "supportAccess", [
        "support_grant.approve",
      ]),
    ],
  },
  {
    id: "developer",
    pages: [
      // The API clients are a tenant-wide object; the webhooks are the workspace's.
      settingsPage(
        "SF-16:developer",
        "/settings/developer",
        "developer",
        ["api_client.manage", "webhook.manage"],
        true,
        ["webhook.manage"],
      ),
    ],
  },
  {
    id: "ai",
    pages: [
      settingsPage("SF-15:ai", "/settings/ai", "ai", ["settings.manage"]),
      settingsPage("SF-15:ai-call-log", "/settings/ai/call-log", "aiCallLog", [
        "ai.use",
        "settings.manage",
      ]),
    ],
  },
  {
    id: "sandbox",
    pages: [
      workspacePage("SF-15:sandbox", "/settings/sandbox", "sandbox", ["tenant.snapshot"], true),
    ],
  },
];

/**
 * SCR-PERM-01: any listed read permission; an empty list admits every authenticated member. A
 * permission under which the page is the workspace's is asked for all entities, as the page asks it,
 * so that no link leads a holder for named entities to a page that answers "access limited".
 */
export function mayRead(candidate: SettingsPage, access: Access): boolean {
  return (
    candidate.permissions.length === 0 ||
    candidate.permissions.some((code) =>
      candidate.workspaceWide.includes(code)
        ? access.holdsForAll(code)
        : access.holdsAnywhere(code),
    )
  );
}

/** The groups that keep at least one link: readable pages whose routes are built (XR-14). */
export function visibleGroups(
  access: Access,
  built: ReadonlySet<string>,
  groups: readonly SettingsGroup[] = SETTINGS_GROUPS,
): readonly SettingsGroup[] {
  return groups
    .map((group) => ({
      ...group,
      pages: group.pages.filter(
        (candidate) => built.has(candidate.path) && mayRead(candidate, access),
      ),
    }))
    .filter((group) => group.pages.length > 0);
}

const NOTHING_BUILT: ReadonlySet<string> = new Set();

/** The built route paths that `buildRoutes` puts on the shell route's handle (`app/router.tsx`). */
export function useBuiltPaths(): ReadonlySet<string> {
  const matches = useMatches();
  for (const match of matches) {
    const handle: unknown = match.handle;
    if (
      typeof handle === "object" &&
      handle !== null &&
      "built" in handle &&
      handle.built instanceof Set
    ) {
      return handle.built as ReadonlySet<string>;
    }
  }
  return NOTHING_BUILT;
}

export function tenantKey(): QueryKey {
  return queryKey("tenant", "tenant");
}

export function fetchTenant(): Promise<Tenant> {
  return unwrap(api.GET("/api/v1/tenant"));
}

function pageLabel(candidate: SettingsPage): string {
  return t(`settings.index.pages.${candidate.key}.label`);
}

export function SettingsIndex() {
  const me = useMe();
  const access = useAccess();
  const built = useBuiltPaths();
  const title = t("settings.index.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={4} />;
  } else {
    body = (
      <>
        {access.holdsForAll(SETUP_PERMISSION) ? <SetupBanner built={built} /> : null}
        {visibleGroups(access, built).map((group) => (
          <GroupSection key={group.id} group={group} />
        ))}
      </>
    );
  }

  return (
    <div
      data-testid="SF-15-page"
      className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {body}
    </div>
  );
}

/** DS-CMP-29 info banner while setup is incomplete (BR-PLT-02); "Finish setup" once SF-15:setup is built. */
function SetupBanner({ built }: { readonly built: ReadonlySet<string> }) {
  const tenant = useQuery({ queryKey: tenantKey(), queryFn: fetchTenant });
  if (tenant.data === undefined || tenant.data.setup_completed_at !== null) {
    return null;
  }
  return (
    <div data-testid="SF-15-banner-setup">
      <Banner
        tone="info"
        title={t("settings.index.setup.title")}
        actions={
          built.has(SETUP_PATH) ? (
            <Link
              to={SETUP_PATH}
              className="text-body-sm font-medium text-accent-fg hover:underline"
            >
              {t("settings.index.setup.finish")}
            </Link>
          ) : undefined
        }
      />
    </div>
  );
}

/** One group: `section` named by its `h2`, links in a static table without column headers. */
function GroupSection({ group }: { readonly group: SettingsGroup }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t(`settings.index.groups.${group.id}`)}
      </h2>
      <table aria-labelledby={headingId} className="w-full border-collapse text-body-sm">
        <tbody>
          {group.pages.map((candidate) => {
            const label = pageLabel(candidate);
            return (
              <tr
                key={candidate.screen}
                data-testid={`SF-15-row-${testIdKey(label)}`}
                className="border-b border-hairline"
              >
                <th scope="row" className="w-56 py-2.5 pe-4 text-start align-top font-medium">
                  <Link to={candidate.path} className="text-accent-fg hover:underline">
                    {label}
                  </Link>
                </th>
                <td className="py-2.5 align-top text-fg-2">
                  {candidate.described
                    ? t(`settings.index.pages.${candidate.key}.description`)
                    : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

export interface SettingsPageHeaderProps {
  readonly title: string;
  /** The group whose route tab bar the page renders (SCR-IA-03). */
  readonly group: SettingsGroupId;
  /** A line below the title, for example the profile identity. */
  readonly children?: ReactNode;
  /** The page's command at the end of the title line, for example "Create sandbox copy". */
  readonly actions?: ReactNode;
}

/** SCR-IA-03: the breadcrumb "Settings /", the page `h1` and the route tabs of the page's group. */
export function SettingsPageHeader({ title, group, children, actions }: SettingsPageHeaderProps) {
  const built = useBuiltPaths();
  const access = useAccess();
  const pages = SETTINGS_GROUPS.find((candidate) => candidate.id === group)?.pages ?? [];
  const tabs: RouteTab[] = pages
    .filter((candidate) => built.has(candidate.path) && mayRead(candidate, access))
    .map((candidate) => ({
      id: candidate.screen,
      label: pageLabel(candidate),
      to: candidate.path,
      end: true,
    }));
  const settings = t("settings.index.title");

  return (
    <>
      <header className="flex flex-col gap-1">
        <nav aria-label={t("common.record.breadcrumb")}>
          <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
            <li className="flex items-center gap-1.5">
              {built.has(SETTINGS_PATH) ? (
                <Link to={SETTINGS_PATH} className="hover:text-fg-1 hover:underline">
                  {settings}
                </Link>
              ) : (
                <span>{settings}</span>
              )}
              <span aria-hidden="true">/</span>
            </li>
          </ol>
        </nav>
        {actions === null || actions === undefined ? (
          <h1 tabIndex={-1} className="text-title-lg text-fg-1">
            {title}
          </h1>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <h1 tabIndex={-1} className="text-title-lg text-fg-1">
              {title}
            </h1>
            <span className="ms-auto">{actions}</span>
          </div>
        )}
        {children}
      </header>
      {tabs.length > 1 ? (
        <RouteTabs label={t(`settings.index.groups.${group}`)} tabs={tabs} />
      ) : null}
    </>
  );
}
