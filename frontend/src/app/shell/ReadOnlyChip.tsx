// Read-only chip (SCREENS SCR-PERM-06; PRD BR-UX-04; DESIGN_SYSTEM DS-CMP-01 item 5). A user whose
// permissions in the active tenant (`GET /me` `permissions`) hold no command permission sees the neutral
// chip "Read-only access" after the sandbox indicator, with a tooltip naming what the roles allow.
import { LockSimple } from "../../components/icons/registry";
import { ToneChip } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import { t } from "../../lib/i18n/t";

/**
 * T-PLT-11 codes that view records or run reports: the grants of the PRD §5.6 Viewer and Auditor roles.
 * Every other code is a command permission (L1-4-Q-17).
 */
export const NON_COMMAND_PERMISSIONS: ReadonlySet<string> = new Set([
  "contract.read",
  "ssp.read",
  "config.read",
  "audit.read",
  "report.run",
  "report.export",
  "evidence.export",
  "ai.use",
]);

export function holdsCommandPermission(permissions: readonly string[]): boolean {
  return permissions.some((code) => !NON_COMMAND_PERMISSIONS.has(code));
}

export interface ReadOnlyChipProps {
  readonly permissions: readonly string[];
}

export function ReadOnlyChip({ permissions }: ReadOnlyChipProps) {
  if (holdsCommandPermission(permissions)) {
    return null;
  }
  return (
    <Tooltip content={t("shell.readOnly.tooltip")}>
      {(trigger) => (
        // The chip takes focus so that keyboard users reach its tooltip (DS-CMP-27).
        <span
          {...trigger}
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
          tabIndex={0}
          className="inline-flex rounded-sm"
        >
          <ToneChip tone="neutral" icon={LockSimple} label={t("shell.readOnly.chip")} />
        </span>
      )}
    </Tooltip>
  );
}
