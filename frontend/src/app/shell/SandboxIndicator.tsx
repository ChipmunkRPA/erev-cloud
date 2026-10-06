// Sandbox indicator (SCREENS §1.3 SF-23, SCR-ST-11; DESIGN_SYSTEM DS-CMP-01 item 4; PRD BR-UX-03). In a
// `sandbox` tenant the top bar shows the warning chip "Sandbox: <tenant name>" and a 2 px
// `--warning-solid` line along its top edge; the global banner of the same state is `SandboxBanner`.
// The line always sits beside the chip label (SCREENS §1.1, C76 note).
import { useQuery } from "@tanstack/react-query";

import { WarningCircle } from "../../components/icons/registry";
import { ToneChip } from "../../components/ui/StatusChip";
import { queryKeys } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { fetchSession, type SessionState } from "../auth/RequireSession";

/** The session of the shell, from the cache that the session loader fills (API-S-Session). */
export function useShellSession(): SessionState | undefined {
  return useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession }).data;
}

/** The display name of the active tenant when its kind is `sandbox`, else null. */
export function sandboxTenantName(session: SessionState | undefined): string | null {
  if (session?.authenticated !== true || session.active_tenant === null) {
    return null;
  }
  return session.active_tenant.kind === "sandbox" ? session.active_tenant.display_name : null;
}

export interface SandboxIndicatorProps {
  readonly tenantName: string;
}

/** DS-CMP-01 item 4; the owning header is positioned, so the line spans its top edge. */
export function SandboxIndicator({ tenantName }: SandboxIndicatorProps) {
  return (
    <>
      <span
        aria-hidden="true"
        data-sandbox-line=""
        className="pointer-events-none absolute start-0 end-0 top-0 h-0.5 bg-warning-solid"
      />
      <ToneChip
        tone="warning"
        icon={WarningCircle}
        label={t("shell.sandbox.chip", { tenant: tenantName })}
      />
    </>
  );
}
