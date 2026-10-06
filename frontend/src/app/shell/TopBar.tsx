// Top bar (DESIGN_SYSTEM DS-CMP-01 items 1 to 9; SCREENS §1.1): the context pill, the search trigger and
// command palette, flexible space, the sandbox indicator, "Read-only access", the notifications bell,
// the Help menu and the user menu. RFD-19 adds the bound context pill first (BUILD_SPEC BS1-D-34).
// "Ask about revenue" (item 6) renders with SF-28 once AI is built (XR-14; L1-4-Q-20).
import { useMe } from "../../lib/api/queries/me";
import { CommandPalette } from "./CommandPalette";
import { AccountingContextPill } from "./ContextPill";
import { HelpMenu } from "./HelpMenu";
import { NotificationsPanel } from "./NotificationsPanel";
import { ReadOnlyChip } from "./ReadOnlyChip";
import { SandboxIndicator, sandboxTenantName, useShellSession } from "./SandboxIndicator";
import { UserMenu } from "./UserMenu";

export interface TopBarProps {
  readonly built: ReadonlySet<string>;
  readonly homePath: string;
}

export function TopBar({ built, homePath }: TopBarProps) {
  const session = useShellSession();
  const me = useMe();
  const sandbox = sandboxTenantName(session);
  return (
    <>
      <AccountingContextPill />
      <CommandPalette built={built} />
      <div className="min-w-0 flex-1" />
      {sandbox === null ? null : <SandboxIndicator tenantName={sandbox} />}
      {me.data === undefined ? null : <ReadOnlyChip permissions={me.data.permissions} />}
      <NotificationsPanel built={built} />
      <HelpMenu />
      <UserMenu built={built} homePath={homePath} />
    </>
  );
}
