// SF-05 "Lock period" (SCREENS_B §1.1 J-13.14; §0.3 SB-R-05; SCREENS SCR-PERM-05; DESIGN_SYSTEM
// DS-CMP-11, DS-CMP-19; 04 API-R-09 `POST /approvals/{id}/approve`, §16.8 `request-lock`; PRD SM-07,
// BR-CLS-02, BR-PLT-06, ERR-02, ERR-04, ERR-14, ERR-28; BUILD_SPEC CLO-23, CLO-6), with the close gate
// helpers the cockpit and its dialogs share: gate labels, the failing gates and the static "Close
// gates" table. Locking approves the pending PERIOD_LOCK request with the subject hash the approver
// reviewed; the decision executes the lock. A 403 `mfa-step-up-required` opens the step-up modal and
// the approval is sent again with the same Idempotency-Key and the typed reason (SCR-PERM-05); a 409
// `stale-approval` offers "Reload"; a 409 `lock-conflict` is "busy, try again" (ERR-52), not a failed
// lock: the next press goes out under a new key, because the API keeps that refusal as the answer of the
// first one (dev-guide DG-KRN-IDEM-03).
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import {
  type ApprovalApproveIn,
  APPROVALS_PATH,
  EVERY_APPROVAL,
} from "../../lib/api/queries/approvals";
import {
  type ChecklistItem,
  EVERY_PERIOD,
  type PeriodApproval,
} from "../../lib/api/queries/periods";
import { t } from "../../lib/i18n/t";
import { StepUpModal } from "../settings/profile";

/** E-60 literals that clear a gate for lock. */
const CLEARED: ReadonlySet<string> = new Set(["PASSED", "WAIVED", "NOT_APPLICABLE"]);

export function isCleared(item: Pick<ChecklistItem, "status">): boolean {
  return CLEARED.has(item.status);
}

/** The SCREENS_B §1.1 gate label of a system gate, or the name of a tenant-defined task. */
export function gateLabel(item: Pick<ChecklistItem, "gate_check_code" | "name">): string {
  return item.gate_check_code === null ? item.name : t(`close.gate.${item.gate_check_code}`);
}

/** The certification gate: the lock certifies, so it never fails the lock (CLO-6; ERR-14). */
const CERTIFICATION_GATE = "CONTROLLER_CERTIFIED";

/**
 * The blocking gates and tasks that have not passed, in checklist order, other than
 * CONTROLLER_CERTIFIED ([J] D-88 L7-2-Q-16): the lock guard, the reason-line count and its links.
 * The KPI "Checklist <passed> of <total> passed" and the static "Close gates" table still count and
 * list the certification row.
 */
export function failingGates(checklist: readonly ChecklistItem[]): readonly ChecklistItem[] {
  return checklist.filter(
    (item) => item.is_blocking && !isCleared(item) && item.gate_check_code !== CERTIFICATION_GATE,
  );
}

/** SCR-TID-03: the checklist row key, the gate check code or the task code. */
export function checklistRowKey(item: Pick<ChecklistItem, "gate_check_code" | "code">): string {
  return item.gate_check_code ?? item.code;
}

export function ChecklistChip({ status }: { readonly status: ChecklistItem["status"] }) {
  const chip = chipFor("E-60", status);
  return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
}

const CELL = "px-3 py-2 text-body-sm";

/** The static "Close gates" table of the submit-for-lock and lock dialogs (label, chip). */
export function GateTable({ checklist }: { readonly checklist: readonly ChecklistItem[] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-hairline">
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("close.gates.caption")}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
              {t("close.gates.column.gate")}
            </th>
            <th scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
              {t("close.gates.column.status")}
            </th>
          </tr>
        </thead>
        <tbody>
          {checklist
            .filter((item) => item.is_blocking)
            .map((item) => (
              <tr key={item.id} className="border-b border-hairline last:border-b-0">
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {gateLabel(item)}
                </th>
                <td className={CELL}>
                  <ChecklistChip status={item.status} />
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

export interface LockPeriodDialogProps {
  readonly request: PeriodApproval;
  readonly checklist: readonly ChecklistItem[];
  readonly entityCode: string;
  readonly periodLabel: string;
  readonly nextPeriodLabel: string;
  readonly onClose: () => void;
}

/**
 * SB-R-05 confirmation: close gates, "Reason (required)", Danger "Lock period". The refusals of the
 * decision are shown in the dialog: `self-approval` (ERR-02), `close-gates-failed` with its gates
 * (ERR-14) and `stale-approval` (ERR-04) with "Reload", which reads the period and its requests again.
 * A `lock-conflict` (ERR-52) is a warning: the decision does not wait for the next period's row (04
 * DB-07), nothing was saved, and "Lock period" sends the same approval again under a new key.
 */
export function LockPeriodDialog({
  request,
  checklist,
  entityCode,
  periodLabel,
  nextPeriodLabel,
  onClose,
}: LockPeriodDialogProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${APPROVALS_PATH}/${request.id}/approve`,
    invalidates: [EVERY_PERIOD, EVERY_APPROVAL],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await command.submit({
      subject_content_sha256: request.subject.content_sha256,
      ...(request.impact_preview === null
        ? {}
        : { impact_preview_sha256: request.impact_preview.sha256 }),
      comment: reason.trim(),
    } satisfies ApprovalApproveIn);
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({
        tone: "positive",
        message: t("close.lock.done", { entity: entityCode, period: periodLabel }),
      });
      onClose();
    } else if (outcome.kind === "failed" && outcome.problem.slug === "mfa-step-up-required") {
      setStepUp(true);
    }
  };
  const reload = async () => {
    await Promise.all(
      [EVERY_PERIOD, EVERY_APPROVAL].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
    onClose();
  };
  if (stepUp) {
    // SCR-PERM-05: the dialog keeps its reason and its command while the code is verified, so the
    // approval goes out again with the same Idempotency-Key and body.
    return (
      <StepUpModal
        onCancel={() => setStepUp(false)}
        onVerified={() => {
          setStepUp(false);
          void submit();
        }}
      />
    );
  }
  const problem = command.problem;
  const stale = problem !== null && problem.slug === "stale-approval";
  const busy = problem !== null && problem.slug === "lock-conflict";
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.lock.title", { entity: entityCode, period: periodLabel })}
      description={t("close.lock.description", {
        entity: entityCode,
        period: periodLabel,
        next: nextPeriodLabel,
      })}
      primaryAction={{
        label: t("close.action.lock"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
      testId="SF-05-dialog-lock"
    >
      <div className="flex flex-col gap-3">
        {stale ? (
          <Banner
            tone="negative"
            announce="live"
            title={problem.title}
            actions={
              <Button variant="link" onClick={() => void reload()}>
                {t("close.lock.reload")}
              </Button>
            }
          >
            {problem.detail === null ? null : <p>{problem.detail}</p>}
          </Banner>
        ) : busy ? (
          <Banner tone="warning" announce="live" title={problem.title}>
            {problem.detail === null ? null : <p>{problem.detail}</p>}
          </Banner>
        ) : problem !== null && problem.slug === "mfa-step-up-required" ? null : (
          <RefusalBanner problem={problem} conflict={command.banner} />
        )}
        <GateTable checklist={checklist} />
        <ReasonField
          name="period-lock-reason"
          label={t("close.lock.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}
