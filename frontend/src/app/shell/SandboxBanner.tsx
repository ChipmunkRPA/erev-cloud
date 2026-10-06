// Sandbox banner (SCREENS §0.7 SCR-ST-11; DESIGN_SYSTEM DS-CMP-29; PRD BR-UX-03; 03 REQ-PLT-003;
// BUILD_SPEC SNP-5). In a `sandbox` tenant the global banner region of every screen shows "Sandbox:
// <tenant name>. Nothing here posts or exports."; any other tenant shows nothing there. The kind is
// the session's (`GET /session` `active_tenant.kind`, which the API also names in the response header
// `X-Erev-Tenant-Kind`): every member has it, whereas `GET /tenant` needs `settings.manage`.
import { Banner } from "../../components/feedback/Banner";
import { t } from "../../lib/i18n/t";
import { sandboxTenantName, useShellSession } from "./SandboxIndicator";

/** SCR-ST-11: the global banner of a sandbox tenant; nothing in any other tenant. */
export function SandboxBanner() {
  const tenantName = sandboxTenantName(useShellSession());
  if (tenantName === null) {
    return null;
  }
  return (
    <Banner
      tone="warning"
      global
      announce="static"
      title={t("shell.sandbox.banner", { tenant: tenantName })}
    />
  );
}
