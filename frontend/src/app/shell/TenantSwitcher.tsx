// Tenant switcher (SCREENS §1.3 SF-23; 04 API-R-01 `POST /session/tenant`, §16.12 API-S-Me memberships).
// Opened by the user menu item "Switch tenant": a listbox popover of the user's workspaces by display
// name, the current one marked "Current" and sandbox tenants with the chip "Sandbox". Selecting another
// workspace sends `POST /session/tenant`, clears the query cache, keeps the answered session, opens the
// landing route (BS-D-08) and announces "Switched to <tenant name>". The popover ends with the link "All
// workspaces" to SF-23:select once that route is built (XR-14). The current workspace is the session's
// and every option is a workspace (`open-workspace.ts`): a workspace and its sandbox copies hold one
// membership id, which names none of them.
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useCommand } from "../../lib/api/commands";
import type { MeMembership } from "../../lib/api/queries/me";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { ListboxPopover, type PopoverOption } from "./ListboxPopover";

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

export const SESSION_TENANT_PATH = "/api/v1/session/tenant";
/** SCREENS RT-06 SF-23:select. */
export const SELECT_WORKSPACE_PATH = "/select-workspace";

export interface TenantSwitcherProps {
  readonly memberships: readonly MeMembership[];
  /** The workspace the session is in (`openTenantId`). */
  readonly openTenantId: string | null;
  readonly homePath: string;
  readonly built: ReadonlySet<string>;
  readonly onClose: (returnFocus: boolean) => void;
}

/**
 * The workspaces a user can open: ACTIVE memberships of ACTIVE workspaces (04 §16.12 rev 1.125;
 * an archived sandbox, or one whose copy has not completed, cannot be opened — 05 SBX-07), and
 * the current one whatever its status.
 */
export function switchableMemberships(
  memberships: readonly MeMembership[],
  openTenantId: string | null,
): readonly MeMembership[] {
  return memberships.filter(
    (membership) =>
      (membership.status === "ACTIVE" && membership.tenant.status === "ACTIVE") ||
      membership.tenant.id === openTenantId,
  );
}

export function TenantSwitcher({
  memberships,
  openTenantId,
  homePath,
  built,
  onClose,
}: TenantSwitcherProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { submit, pending, problem } = useCommand<SessionLoginOut>({
    method: "POST",
    path: SESSION_TENANT_PATH,
  });
  const choices = switchableMemberships(memberships, openTenantId);
  const options: PopoverOption[] = choices.map((membership) => {
    const current = membership.tenant.id === openTenantId;
    const sandbox = membership.tenant.kind === "sandbox";
    return {
      id: membership.tenant.id,
      label: membership.tenant.display_name,
      extra:
        current || sandbox ? (
          <>
            {sandbox ? <StatusChip status="Sandbox" /> : null}
            {current ? <OutlineChip label={t("shell.tenantSwitcher.current")} /> : null}
          </>
        ) : undefined,
    };
  });

  const select = async (tenantId: string) => {
    const membership = choices.find((candidate) => candidate.tenant.id === tenantId);
    if (membership === undefined || pending) {
      return;
    }
    if (tenantId === openTenantId) {
      onClose(true);
      return;
    }
    const outcome = await submit({ tenant_id: membership.tenant.id });
    if (outcome.kind !== "succeeded") {
      return;
    }
    // Every cached read belongs to the previous workspace (DG-FE-04 scopes).
    queryClient.clear();
    if (outcome.data !== null) {
      queryClient.setQueryData(queryKeys.session(), outcome.data);
    }
    onClose(false);
    void navigate(homePath);
    announce(
      t("shell.tenantSwitcher.switched", { tenant: membership.tenant.display_name }),
      "polite",
    );
  };

  const footer =
    problem === null && !built.has(SELECT_WORKSPACE_PATH) ? undefined : (
      <div className="flex flex-col gap-1.5">
        {problem === null ? null : (
          <p role="alert" className="text-body-sm text-negative-fg">
            {problem.title}
          </p>
        )}
        {built.has(SELECT_WORKSPACE_PATH) ? (
          <Link
            to={SELECT_WORKSPACE_PATH}
            onClick={() => {
              onClose(false);
            }}
            className="text-body-sm text-accent-fg hover:underline"
          >
            {t("shell.tenantSwitcher.allWorkspaces")}
          </Link>
        ) : null}
      </div>
    );

  return (
    <ListboxPopover
      label={t("shell.tenantSwitcher.label")}
      options={options}
      selectedId={openTenantId}
      onSelect={(id) => {
        void select(id);
      }}
      onClose={onClose}
      footer={footer}
      className="end-0"
    />
  );
}
