// Parts the audit log and the verification record share (SCREENS_B §6.3, §6.4; §0.4 E-98; SCREENS §0.6
// SCR-PERM-01, SCR-PERM-07; DESIGN_SYSTEM DS-CMP-19, DS-CMP-23; BUILD_SPEC RPS-21): the access-limited
// state of `audit.read`, the E-98 chip word of a verification result, the failure title, the trigger
// label and a recorded JSON value as text.
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { chipFor, type StatusWord } from "../../components/ui/StatusChip";
import { AUDIT_READ_PERMISSION, type AuditVerification } from "../../lib/api/queries/audit";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";

/**
 * SCR-PERM-01 for `audit.read` (SCREENS_B §6.3 SCR-ST-06). `allEntities` is the state of a member who
 * holds the permission, but not for all entities, or whose read the API refused: the log covers every
 * entity of the workspace (ruling R-28), and the description says what to ask for.
 */
export function AuditAccessLimited({ allEntities = false }: { readonly allEntities?: boolean }) {
  return (
    <AccessLimited
      area={t("evidence.access.auditLog")}
      permissions={[AUDIT_READ_PERMISSION]}
      allEntities={
        allEntities
          ? { message: "evidence.access.allEntities", permission: AUDIT_READ_PERMISSION }
          : undefined
      }
    />
  );
}

/** SCREENS_B §0.4 E-98: the chip word of a chain verification result. */
export function resultWord(result: AuditVerification["result"]): StatusWord {
  return result === "NOT_APPLICABLE"
    ? "Not applicable"
    : (chipFor("E-98", result)?.status ?? "Not applicable");
}

/** SCREENS_B §6.3 "Verification failed (latest)": "Audit chain verification failed at event <n>". */
export function failureTitle(verification: Pick<AuditVerification, "first_failure_seq">): string {
  return verification.first_failure_seq === null
    ? t("evidence.auditLog.chain.failedNoEvent")
    : t("evidence.auditLog.chain.failed", {
        event: formatNumber(verification.first_failure_seq, { kind: "count" }),
      });
}

/** SCREENS_B §6.4 "Trigger": "Scheduled" or "On demand". */
export function triggerLabel(trigger: AuditVerification["trigger"]): string {
  return t(`evidence.verification.trigger.${trigger}`);
}

/** A recorded value as text: a string as it is, anything else as JSON; null has no text. */
export function recordedText(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "string") {
    return value === "" ? '""' : value;
  }
  return JSON.stringify(value);
}
