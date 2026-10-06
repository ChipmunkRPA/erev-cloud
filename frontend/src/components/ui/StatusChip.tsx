// Status chip (DESIGN_SYSTEM DS-CMP-19): the only mapping from a status word to its tone and icon.
// `chipFor` maps 04 enumeration literals to words per SCREENS §0.8 and SCREENS_B §0.4 (where both map
// a literal, SCREENS §0.8 governs). Unknown words and literals throw (BUILD_SPEC XR-12).
import { t } from "../../lib/i18n/t";
import { type Icon, ICONS, type IconName } from "../icons/registry";
import { cn } from "./cn";

export type ChipTone = "neutral" | "info" | "positive" | "warning" | "negative";

interface ChipDefinition {
  readonly tone: ChipTone;
  readonly icon: IconName;
  readonly dashed?: boolean;
}

export const VOCABULARY = {
  Draft: { tone: "neutral", icon: "PencilSimpleLine" },
  "Pending approval": { tone: "info", icon: "HourglassMedium" },
  Approved: { tone: "positive", icon: "CheckCircle" },
  Rejected: { tone: "negative", icon: "XCircle" },
  Withdrawn: { tone: "neutral", icon: "ArrowUUpLeft" },
  Stale: { tone: "warning", icon: "ClockCounterClockwise" },
  Active: { tone: "neutral", icon: "Circle" },
  Void: { tone: "neutral", icon: "Prohibit" },
  "On hold": { tone: "warning", icon: "PauseCircle" },
  Satisfied: { tone: "positive", icon: "CheckCircle" },
  Valid: { tone: "positive", icon: "CheckCircle" },
  Warning: { tone: "warning", icon: "WarningCircle" },
  Error: { tone: "negative", icon: "XCircle" },
  "Period open": { tone: "neutral", icon: "LockSimpleOpen" },
  "Soft close": { tone: "warning", icon: "HourglassMedium" },
  Locked: { tone: "neutral", icon: "LockSimple" },
  Reopened: { tone: "warning", icon: "LockSimpleOpen" },
  Queued: { tone: "neutral", icon: "CircleDashed" },
  Running: { tone: "info", icon: "CircleHalf" },
  Succeeded: { tone: "positive", icon: "CheckCircle" },
  Failed: { tone: "negative", icon: "XCircle" },
  Exported: { tone: "info", icon: "ArrowSquareOut" },
  Posted: { tone: "positive", icon: "CheckCircle" },
  Reconciled: { tone: "positive", icon: "CheckCircle" },
  Difference: { tone: "negative", icon: "Equals" },
  Sandbox: { tone: "warning", icon: "WarningCircle" },
  Proposed: { tone: "neutral", icon: "Sparkle", dashed: true },
  Abandoned: { tone: "neutral", icon: "Prohibit" },
  Accepted: { tone: "positive", icon: "CheckCircle" },
  "Account locked": { tone: "warning", icon: "LockSimple" },
  Aggregated: { tone: "neutral", icon: "TreeStructure" },
  Applied: { tone: "positive", icon: "CheckCircle" },
  Archived: { tone: "neutral", icon: "Prohibit" },
  "Auto-certified": { tone: "positive", icon: "CheckCircle" },
  Balanced: { tone: "positive", icon: "CheckCircle" },
  Blank: { tone: "neutral", icon: "Minus" },
  Blocked: { tone: "warning", icon: "PauseCircle" },
  Blocking: { tone: "negative", icon: "XCircle" },
  "Budget exceeded": { tone: "warning", icon: "WarningCircle" },
  Calculated: { tone: "neutral", icon: "PencilSimpleLine" },
  Cancelled: { tone: "neutral", icon: "Prohibit" },
  Certified: { tone: "positive", icon: "CheckCircle" },
  Committed: { tone: "positive", icon: "CheckCircle" },
  Completed: { tone: "positive", icon: "CheckCircle" },
  Denied: { tone: "negative", icon: "XCircle" },
  Disabled: { tone: "neutral", icon: "Prohibit" },
  Dismissed: { tone: "neutral", icon: "Prohibit" },
  Expired: { tone: "neutral", icon: "ClockCounterClockwise" },
  Future: { tone: "neutral", icon: "CalendarBlank" },
  Imported: { tone: "info", icon: "CheckCircle" },
  "In progress": { tone: "info", icon: "CircleHalf" },
  "In review": { tone: "info", icon: "CircleHalf" },
  Info: { tone: "info", icon: "Info" },
  Invited: { tone: "info", icon: "HourglassMedium" },
  Met: { tone: "positive", icon: "CheckCircle" },
  "Not a contract": { tone: "neutral", icon: "Prohibit" },
  "Not applicable": { tone: "neutral", icon: "Minus" },
  "Not mapped": { tone: "warning", icon: "WarningCircle" },
  "Not passed": { tone: "negative", icon: "XCircle" },
  "Not started": { tone: "neutral", icon: "Circle" },
  Open: { tone: "neutral", icon: "Circle" },
  Pass: { tone: "positive", icon: "CheckCircle" },
  Passed: { tone: "positive", icon: "CheckCircle" },
  "Pending review": { tone: "info", icon: "HourglassMedium" },
  "Permanently locked": { tone: "neutral", icon: "LockSimple" },
  Prepared: { tone: "info", icon: "HourglassMedium" },
  Profiled: { tone: "info", icon: "CheckCircle" },
  Promoted: { tone: "positive", icon: "CheckCircle" },
  Published: { tone: "positive", icon: "CheckCircle" },
  Removed: { tone: "neutral", icon: "Prohibit" },
  Resolved: { tone: "positive", icon: "CheckCircle" },
  "Revocation requested": { tone: "warning", icon: "WarningCircle" },
  Reviewed: { tone: "positive", icon: "CheckCircle" },
  Revoked: { tone: "neutral", icon: "Prohibit" },
  Shortfall: { tone: "warning", icon: "WarningCircle" },
  Superseded: { tone: "neutral", icon: "ClockCounterClockwise" },
  Suspended: { tone: "warning", icon: "PauseCircle" },
  Terminated: { tone: "neutral", icon: "Prohibit" },
  Tested: { tone: "info", icon: "CheckCircle" },
  "Timed out": { tone: "warning", icon: "ClockCounterClockwise" },
  "Verification failed": { tone: "negative", icon: "XCircle" },
  Verified: { tone: "positive", icon: "ShieldCheck" },
  Waived: { tone: "neutral", icon: "CheckCircle" },
} as const satisfies Readonly<Record<string, ChipDefinition>>;

export type StatusWord = keyof typeof VOCABULARY;

export function isStatusWord(word: string): word is StatusWord {
  return Object.hasOwn(VOCABULARY, word);
}

/** The catalogue key of a word: `common.status.<camelCase word>`, for example `pendingApproval`. */
export function statusMessageKey(word: StatusWord): string {
  const parts = word.split(/[^A-Za-z0-9]+/).filter((part) => part !== "");
  const camel = parts
    .map((part, index) =>
      index === 0
        ? part.toLowerCase()
        : `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`,
    )
    .join("");
  return `common.status.${camel}`;
}

const TONE_CLASS: Readonly<Record<ChipTone, string>> = {
  neutral: "bg-neutral-chip-bg text-fg-2 border-default",
  info: "bg-info-bg text-info-fg border-info-border",
  positive: "bg-positive-bg text-positive-fg border-positive-border",
  warning: "bg-warning-bg text-warning-fg border-warning-border",
  negative: "bg-negative-bg text-negative-fg border-negative-border",
};

export interface StatusChipProps {
  readonly status: string;
  /** A caption beside the chip, for example "Calculating" (SCREENS_B §0.4). */
  readonly caption?: string | null | undefined;
}

export function StatusChip({ status, caption }: StatusChipProps) {
  if (!isStatusWord(status)) {
    throw new Error(`"${status}" is not DS-CMP-19 status vocabulary`);
  }
  const definition: ChipDefinition = VOCABULARY[status];
  const ChipIcon = ICONS[definition.icon];
  const chip = (
    <span
      data-tone={definition.tone}
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 text-caption font-medium",
        TONE_CLASS[definition.tone],
        definition.dashed === true && "border-dashed",
      )}
    >
      <ChipIcon aria-hidden="true" size={12} data-icon={definition.icon} className="shrink-0" />
      {t(statusMessageKey(status))}
    </span>
  );
  if (caption === undefined || caption === null) {
    return chip;
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      {chip}
      <span className="text-caption text-fg-3">{caption}</span>
    </span>
  );
}

/** The outline variant for classifications that are not states ("Ratable", "Legacy v1"). */
export function OutlineChip({ label }: { readonly label: string }) {
  return (
    <span className="inline-flex h-5 items-center whitespace-nowrap rounded-sm border border-default bg-transparent px-1.5 text-caption font-medium text-fg-2">
      {label}
    </span>
  );
}

export interface ToneChipProps {
  readonly tone: ChipTone;
  readonly icon: Icon;
  readonly label: string;
}

/** A tone chip for a notice that is not a status word, for example DS-CH-05 "Over transaction price". */
export function ToneChip({ tone, icon: ChipIcon, label }: ToneChipProps) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 text-caption font-medium",
        TONE_CLASS[tone],
      )}
    >
      <ChipIcon aria-hidden="true" size={12} className="shrink-0" />
      {label}
    </span>
  );
}

export interface ChipSpec {
  readonly status: StatusWord;
  readonly tone: ChipTone;
  readonly icon: IconName;
  readonly caption: string | null;
}

export type ChipContext = Readonly<Record<string, string | number | null | undefined>>;

// SCREENS §0.8 and SCREENS_B §0.4. `null` marks a literal that shows no chip (E-22 UNSATISFIED).
const LITERALS: Readonly<Record<string, Readonly<Record<string, StatusWord | null>>>> = {
  "E-17": {
    DRAFT: "Draft",
    PENDING_REVIEW: "Pending approval",
    ACTIVE: "Active",
    VOIDED: "Void",
    NOT_A_CONTRACT: "Not a contract",
    COMPLETED: "Completed",
    TERMINATED: "Terminated",
  },
  "E-26": {
    DRAFT: "Draft",
    SUBMITTED: "Pending approval",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    VOIDED: "Void",
    APPLIED: "Applied",
  },
  "E-12": {
    DRAFT: "Draft",
    SUBMITTED: "Pending approval",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    WITHDRAWN: "Withdrawn",
    TESTED: "Tested",
    PUBLISHED: "Published",
    SUPERSEDED: "Superseded",
    // A discarded estimate version: ruling R-119 (e), SCREENS §0.8 rev 1.29.
    VOIDED: "Void",
  },
  "E-40": {
    UPLOADED: "Queued",
    VALIDATING: "Running",
    VALIDATED: "Running",
    DIFFING: "Running",
    COMMITTING: "Running",
    INVALID: "Error",
    DIFF_READY: "Valid",
    SUBMITTED: "Pending approval",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    FAILED: "Failed",
    COMMITTED: "Committed",
    CANCELLED: "Cancelled",
  },
  "E-41": {
    VALID: "Valid",
    WARNING: "Warning",
    ERROR: "Error",
    BLANK: "Blank",
    AGGREGATED: "Aggregated",
  },
  "E-43": { BLOCKING: "Blocking", WARNING: "Warning", INFO: "Info" },
  "E-44": {
    OPEN: "Open",
    IN_PROGRESS: "In progress",
    RESOLVED: "Resolved",
    WAIVED: "Waived",
    DISMISSED: "Dismissed",
  },
  "E-05": {
    PENDING: "Pending approval",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    WITHDRAWN: "Withdrawn",
  },
  "E-72": {
    QUEUED: "Queued",
    RUNNING: "Running",
    SUCCEEDED: "Succeeded",
    FAILED: "Failed",
    CONTROL_TOTAL_MISMATCH: "Difference",
  },
  "E-22": {
    SATISFIED: "Satisfied",
    UNSATISFIED: null,
    PARTIALLY_SATISFIED: null,
    CANCELLED: "Cancelled",
  },
  "T-INT-01": { ACTIVE: "Active", DISABLED: "Disabled" },
  "E-57": { REVIEWED: "Reviewed" },
  "E-04": {
    open: "Period open",
    closing: "Soft close",
    closed: "Locked",
    reopened: "Reopened",
    future: "Future",
    permanently_locked: "Permanently locked",
  },
  "E-62": {
    PENDING: "Queued",
    RUNNING: "Running",
    SUCCEEDED: "Succeeded",
    FAILED: "Failed",
    BLOCKED: "Blocked",
    CANCELLED: "Cancelled",
  },
  "E-60": {
    NOT_STARTED: "Not started",
    IN_PROGRESS: "In progress",
    PASSED: "Passed",
    FAILED: "Not passed",
    WAIVED: "Waived",
    NOT_APPLICABLE: "Not applicable",
  },
  "E-59": {
    DRAFT: "Draft",
    CERTIFIED: "Reconciled",
    REOPENED: "Reopened",
    PREPARED: "Prepared",
    AUTO_CERTIFIED: "Auto-certified",
    REVIEWED: "Reviewed",
  },
  "E-34": {
    draft: "Calculated",
    approved: "Approved",
    exported: "Exported",
    failed: "Failed",
    acknowledged: "Posted",
    cancelled: "Cancelled",
  },
  "E-67": { QUEUED: "Queued", RUNNING: "Running", SUCCEEDED: "Succeeded", FAILED: "Failed" },
  "T-RPT-02": { PASS: "Pass", FAIL: "Difference", NOT_APPLICABLE: "Not applicable" },
  "E-98": { PASS: "Verified", FAIL: "Verification failed" },
  "E-76": {
    UPLOADED: "Queued",
    PROFILING: "Running",
    IMPORTING: "Running",
    RECONCILED: "Reconciled",
    SUBMITTED: "Pending approval",
    FAILED: "Failed",
    PROFILED: "Profiled",
    IMPORTED: "Imported",
    PROMOTED: "Promoted",
    CANCELLED: "Cancelled",
  },
  "E-74": {
    proposed: "Proposed",
    failed: "Failed",
    accepted: "Accepted",
    rejected: "Dismissed",
    expired: "Expired",
  },
  "E-78": { ACTIVE: "Active", INVITED: "Invited", SUSPENDED: "Suspended", REMOVED: "Removed" },
  "E-102": { LOCKED: "Account locked" },
  "SMAP-14": { requested: "Pending approval", active: "Active", revoked: "Revoked" },
  "E-96": {
    REQUESTED: "Pending approval",
    APPROVED: "Approved",
    REJECTED: "Rejected",
    REVOKED: "Revoked",
    EXPIRED: "Expired",
  },
  "E-107": {
    DRAFT: "Draft",
    IN_REVIEW: "In review",
    COMPLETED: "Completed",
    CANCELLED: "Cancelled",
  },
  "E-108": {
    PENDING: "Pending review",
    CERTIFIED: "Certified",
    REVOKE_REQUESTED: "Revocation requested",
    REVOKED: "Revoked",
  },
  // PENDING_APPROVAL and REJECTED: ruling R-113 (e), SCREENS_B §0.4 rev 1.59.
  "E-103": {
    PENDING_APPROVAL: "Pending approval",
    ACTIVE: "Active",
    REJECTED: "Rejected",
    REVOKED: "Revoked",
  },
  "E-97": { PENDING: "Queued", SUCCEEDED: "Succeeded", FAILED: "Failed", ABANDONED: "Abandoned" },
  "E-100": { ACTIVE: "Active", ARCHIVED: "Archived" },
  "E-16": { sandbox: "Sandbox" },
  "E-101": { ARCHIVED: "Archived" },
};

const ACTIVE_JOB = new Set(["QUEUED", "RUNNING"]);

function spec(status: StatusWord, caption: string | null = null): ChipSpec {
  const definition: ChipDefinition = VOCABULARY[status];
  return { status, tone: definition.tone, icon: definition.icon, caption };
}

// Literals whose chip depends on related state (SCREENS §0.8 E-05, E-40; SCREENS_B §0.4 E-34, E-74).
function contextual(enumId: string, literal: string, context: ChipContext): ChipSpec | undefined {
  if (enumId === "E-05" && literal === "VOIDED") {
    // STALE_SUBJECT shows Stale; SUBJECT_VOIDED and WITHDRAWN_BY_PREPARER show Void (SPEC-Q-202).
    return spec(context.void_reason === "STALE_SUBJECT" ? "Stale" : "Void");
  }
  if (enumId === "E-40" && literal === "INVALID") {
    return spec("Error", t("common.status.caption.importInvalid"));
  }
  if (enumId === "E-34") {
    const jobActive = typeof context.job_state === "string" && ACTIVE_JOB.has(context.job_state);
    if (literal === "draft" && jobActive) {
      return spec("Running", t("common.status.caption.calculating"));
    }
    if (literal === "draft" && context.request_status === "PENDING") {
      return spec("Pending approval", t("common.status.caption.submitted"));
    }
    if (literal === "approved" && jobActive) {
      return spec("Running", t("common.status.caption.exporting"));
    }
    const acknowledged = context.acknowledged_batches;
    if (literal === "exported" && typeof acknowledged === "number" && acknowledged > 0) {
      return spec(
        "Exported",
        t("common.status.caption.partiallyAcknowledged", {
          acknowledged,
          total: context.batch_count ?? acknowledged,
        }),
      );
    }
  }
  if (enumId === "E-74" && literal === "proposed" && context.request_status === "PENDING") {
    return spec("Pending approval");
  }
  return undefined;
}

/** The chip of an 04 literal, or null where the screens show none. Unknown literals throw. */
export function chipFor(
  enumId: string,
  literal: string,
  context: ChipContext = {},
): ChipSpec | null {
  const special = contextual(enumId, literal, context);
  if (special !== undefined) {
    return special;
  }
  const table = LITERALS[enumId];
  if (table === undefined || !Object.hasOwn(table, literal)) {
    throw new Error(`No status chip for ${enumId} ${literal}`);
  }
  const word = table[literal];
  return word === null || word === undefined ? null : spec(word);
}
