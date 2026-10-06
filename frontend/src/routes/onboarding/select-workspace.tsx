// SF-23:select Choose a workspace (SCREENS_B §11.3; SCREENS §0.4 RT-06, §1.3; 04 API-R-01
// `POST /session/tenant`, §16.12 API-S-Me memberships). A minimal frame without the rail: the page
// lists the ACTIVE memberships in three sections, Production, Demo workspaces, and Sandboxes and
// scenarios, each ordered by `last_opened_at` (newest first, never opened last). "Open <workspace
// name>" sends `POST /session/tenant`, keeps the answered session, opens the landing route (BS-D-08)
// and announces "Switched to <workspace name>". With one membership the page opens it at once; with
// none it says so and offers "Sign out". The Industry, Roles and Source columns and "New scenario"
// are not rendered (SCREENS_B §11.3 defers them; the scenario form is not built, XR-14).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { SESSION_TENANT_PATH } from "../../app/shell/TenantSwitcher";
import { useSignOut } from "../../app/shell/UserMenu";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Button } from "../../components/ui/Button";
import { StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { prepareRequest } from "../../lib/api/client";
import { useCommand } from "../../lib/api/commands";
import { type ApiProblem, readProblem } from "../../lib/api/problems";
import type { Me, MeMembership } from "../../lib/api/queries/me";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { formatDate, instantMs, NO_VALUE, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

export const ME_PATH = "/api/v1/me";

export type WorkspaceSection = "production" | "demo" | "sandbox";

/** SCREENS_B §11.3 section order. */
export const SECTIONS: readonly WorkspaceSection[] = ["production", "demo", "sandbox"];

/** Sandboxes and scenarios by tenant kind; production tenants split on `is_demo` (L3-3-Q-11). */
export function sectionOf(membership: MeMembership): WorkspaceSection {
  if (membership.tenant.kind === "sandbox") {
    return "sandbox";
  }
  return membership.tenant.is_demo ? "demo" : "production";
}

function openedMs(membership: MeMembership): number | null {
  return membership.last_opened_at === null ? null : instantMs(membership.last_opened_at);
}

/**
 * The workspaces a user can open: ACTIVE memberships of ACTIVE workspaces (04 §16.12 rev 1.125;
 * 05 SBX-07) by `last_opened_at` descending, nulls last, then code.
 */
export function openableMemberships(memberships: readonly MeMembership[]): MeMembership[] {
  return memberships
    .filter((membership) => membership.status === "ACTIVE" && membership.tenant.status === "ACTIVE")
    .sort((left, right) => {
      const a = openedMs(left);
      const b = openedMs(right);
      if (a !== b) {
        if (a === null) {
          return 1;
        }
        if (b === null) {
          return -1;
        }
        return b - a;
      }
      return left.tenant.code.localeCompare(right.tenant.code);
    });
}

/** SCREENS SCR-TID-03: lowercase, runs outside `[a-z0-9]` become one hyphen, no edge hyphens. */
export function testIdKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * `GET /me` through the request pipeline, less its 401 redirect, so a refusal shows on the page with
 * Retry and Sign out (L3-3-Q-10). `GET /me` answers a session without a workspace with 200 and its
 * memberships (D-83), which is how sign-in sends a member of several workspaces here.
 */
export async function fetchWorkspaces(): Promise<Me> {
  const request = prepareRequest(
    new Request(new URL(ME_PATH, globalThis.location.origin), { credentials: "same-origin" }),
  );
  const response = await globalThis.fetch(request);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as Me;
}

function lastOpened(membership: MeMembership): string {
  const date =
    membership.last_opened_at === null
      ? NO_VALUE
      : formatDate(timestampDate(membership.last_opened_at));
  return t("onboarding.select-workspace.lastOpened", { date });
}

export function SelectWorkspace() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const signOut = useSignOut();
  const me = useQuery<Me, ApiProblem>({
    queryKey: queryKeys.me(),
    queryFn: fetchWorkspaces,
    retry: false,
  });
  const { submit, problem } = useCommand<SessionLoginOut>({
    method: "POST",
    path: SESSION_TENANT_PATH,
  });
  const titleId = useId();
  const [opening, setOpening] = useState<string | null>(null);
  const busy = useRef(false);
  const autoOpened = useRef(false);
  const title = t("onboarding.select-workspace.title");
  const wordmark = t("shell.wordmark");

  useEffect(() => {
    document.title = t("shell.documentTitle", { title });
  }, [title]);

  const open = useCallback(
    async (membership: MeMembership) => {
      if (busy.current) {
        return;
      }
      busy.current = true;
      // Once any workspace opens, a `GET /me` refetched before this page unmounts must not open
      // its only membership again.
      autoOpened.current = true;
      // A row is a workspace: a workspace and its sandbox copies hold one membership id.
      setOpening(membership.tenant.id);
      const outcome = await submit({ tenant_id: membership.tenant.id });
      busy.current = false;
      setOpening(null);
      if (outcome.kind !== "succeeded") {
        return;
      }
      // Every cached read belonged to the previous session (DG-FE-04 scopes).
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "session" });
      if (outcome.data !== null) {
        queryClient.setQueryData(queryKeys.session(), outcome.data);
      }
      void navigate("/", { replace: true });
      announce(
        t("shell.tenantSwitcher.switched", { tenant: membership.tenant.display_name }),
        "polite",
      );
    },
    [navigate, queryClient, submit],
  );

  const memberships = me.data === undefined ? null : openableMemberships(me.data.memberships);
  const only = memberships !== null && memberships.length === 1 ? memberships[0] : undefined;

  useEffect(() => {
    if (only === undefined || autoOpened.current) {
      return;
    }
    autoOpened.current = true;
    void open(only);
  }, [only, open]);

  let content;
  if (me.isError) {
    content = (
      <Banner
        tone="negative"
        title={me.error.detail ?? me.error.title}
        actions={
          <>
            <Button variant="link" size="sm" onClick={() => void me.refetch()}>
              {t("onboarding.select-workspace.retry")}
            </Button>
            <Button variant="link" size="sm" onClick={() => void signOut()}>
              {t("onboarding.select-workspace.signOut")}
            </Button>
          </>
        }
      />
    );
  } else if (memberships === null) {
    content = <Skeleton region={title} shape="rows" count={4} />;
  } else if (memberships.length === 0) {
    content = (
      <EmptyState
        title={t("onboarding.select-workspace.empty.title")}
        description={t("onboarding.select-workspace.empty.description")}
        action={{
          label: t("onboarding.select-workspace.signOut"),
          onAction: () => {
            void signOut();
          },
        }}
      />
    );
  } else {
    content = SECTIONS.map((section) => {
      const rows = memberships.filter((membership) => sectionOf(membership) === section);
      if (rows.length === 0) {
        return null;
      }
      const headingId = `${titleId}-${section}`;
      return (
        <section key={section} aria-labelledby={headingId} className="flex flex-col gap-2">
          <h2 id={headingId} className="text-title-sm text-fg-1">
            {t(`onboarding.select-workspace.section.${section}`)}
          </h2>
          <table aria-labelledby={headingId} className="w-full border-collapse text-body-sm">
            <tbody>
              {rows.map((membership) => {
                const name = membership.tenant.display_name;
                return (
                  <tr
                    key={membership.tenant.id}
                    data-testid={`SF-23-row-${testIdKey(membership.tenant.code)}`}
                    className="border-b border-hairline"
                  >
                    <th scope="row" className="py-2 pe-4 text-start font-medium text-fg-1">
                      <span className="inline-flex flex-wrap items-center gap-2">
                        {name}
                        {membership.tenant.kind === "sandbox" ? (
                          <StatusChip status="Sandbox" />
                        ) : null}
                      </span>
                    </th>
                    <td className="py-2 pe-4 font-mono text-fg-2">{membership.tenant.code}</td>
                    <td className="py-2 pe-4 text-fg-2 tabular-nums">{lastOpened(membership)}</td>
                    <td className="py-2 text-end">
                      <Button
                        variant="secondary"
                        size="sm"
                        aria-label={t("onboarding.select-workspace.openLabel", {
                          workspace: name,
                        })}
                        loading={opening === membership.tenant.id}
                        onClick={() => void open(membership)}
                      >
                        {t("onboarding.select-workspace.open")}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      );
    });
  }

  return (
    <div className="min-h-dvh bg-canvas text-fg-1">
      <header className="flex h-[var(--topbar-h)] items-center border-b border-hairline bg-surface px-[var(--gutter)]">
        <span role="img" aria-label={wordmark} className="text-title-md text-fg-1">
          {wordmark}
        </span>
      </header>
      <main
        data-testid="SF-23-page"
        aria-labelledby={titleId}
        className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-8"
      >
        <h1 id={titleId} tabIndex={-1} className="text-title-lg text-fg-1">
          {title}
        </h1>
        {problem === null ? null : (
          <Banner tone="negative" title={problem.detail ?? problem.title} />
        )}
        {content}
      </main>
    </div>
  );
}
