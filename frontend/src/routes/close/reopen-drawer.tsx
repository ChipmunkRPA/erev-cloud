// SF-05 "Request reopen" (SCREENS_B §1.1 J-14.1; DESIGN_SYSTEM DS-CMP-09 modal drawer, DS-CMP-18,
// DS-A11Y-08; 04 §16.8 `POST /periods/{id}/request-reopen`, API-R-12 `POST /files` and
// `POST /attachments`, `POST /judgements` and `/submit`; BUILD_SPEC CLO-23, CLO-7). The request is sent
// first; the attachments and the estimate-versus-error judgement follow, and a later failure keeps the
// drawer open with the partial-success banner. While the request waits for its two decisions the
// cockpit shows `ReopenRequestBanner`: the dual-approval status, the decisions recorded so far and, for
// the requester, "Withdraw request". The two optional parts follow the requester's permissions
// (SCR-PERM-02; supervisor ruling R-100): the judgement is the Revenue Accountant's, so its fields render
// for a holder of `judgement.create` and another requester reads who records it and where it is listed;
// the attachments field renders for a holder of an attachment permission.
import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { useCommandKeys } from "../../lib/api/commands";
import type { ApiProblem } from "../../lib/api/problems";
import {
  type ApprovalWithdrawIn,
  fetchApproval,
  useApprovalCommand,
} from "../../lib/api/queries/approvals";
import { ATTACHMENTS_PATH, sendStep } from "../../lib/api/queries/contracts";
import {
  EVERY_PERIOD,
  periodCommandPath,
  type PeriodApproval,
  type PeriodReopenRequestIn,
} from "../../lib/api/queries/periods";
import { uploadFile } from "../../lib/api/queries/ssp-books";
import { type Period, rowIfMatch } from "../../lib/api/queries/tenant";
import { formatDate, formatTimestamp, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { EvidenceField, SelectField } from "../contracts/drawers/common";
import {
  EMPTY_JUDGEMENT,
  type JudgementDraft,
  judgementErrors,
  JudgementFields,
  recordJudgement,
} from "./judgement-drawer";

/** The E-110 subset of 04 table 3.4-R for `request-reopen` (OQ-B-06, D-76). */
export type ReopenReason = "ERROR_CORRECTION" | "LATE_SOURCE_DATA" | "AUDIT_ADJUSTMENT" | "OTHER";
const REASONS: readonly ReopenReason[] = [
  "ERROR_CORRECTION",
  "LATE_SOURCE_DATA",
  "AUDIT_ADJUSTMENT",
  "OTHER",
];
const ATTACHMENT_PURPOSE = "ATTACHMENT";
/**
 * 04 API-R-12: `POST /files` purpose `ATTACHMENT` and `POST /attachments` answer a holder of one of
 * the subject write permissions (`domain/platform/file_access.py` `_SUBJECT_WRITE`), who may attach a
 * file to an approval request they see. "Attachments (optional)" renders for them.
 *
 * Item ATT-REQUESTER-1 (supervisor ruling R-100 (b); lane SECFIX-PLT): whoever submitted an approval
 * request will attach evidence to it while it is pending, whatever other permission they hold. When
 * that is on main the field renders for every requester and THIS LIST GOES — it mirrors a server rule
 * that no API member states, so it must not outlive the item.
 */
export const ATTACHMENT_PERMISSIONS: readonly string[] = [
  "access.approve",
  "adjustment.create",
  "contract.create",
  "estimate.create",
  "event.record",
  "exception.resolve",
  "judgement.create",
  "modification.create",
  "recon.prepare",
  "ssp.create",
  "user.manage",
];

export interface ReopenDrawerProps {
  readonly period: Period;
  readonly periodLabel: string;
  readonly bookLabel: string;
  /** SF-12:request is built, so the success toast may link the request. */
  readonly canViewRequest: boolean;
  /** The viewer holds one of `ATTACHMENT_PERMISSIONS` (SCR-PERM-02). */
  readonly canAttach: boolean;
  /** The viewer holds `judgement.create` (SCR-PERM-02). */
  readonly canJudge: boolean;
  /** SF-08:report `judgement_register` in the period's context, or null while it is not built. */
  readonly judgementRegisterHref: string | null;
  readonly onClose: () => void;
}

export function ReopenDrawer({
  period,
  periodLabel,
  bookLabel,
  canViewRequest,
  canAttach,
  canJudge,
  judgementRegisterHref,
  onClose,
}: ReopenDrawerProps) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  // One press sends the request, its attachments and the judgement record: a second press after a
  // part of it failed replays what succeeded and sends the rest (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const formId = useId();
  const checkboxId = useId();
  const [reason, setReason] = useState<ReopenReason | null>(null);
  const [comment, setComment] = useState("");
  const [files, setFiles] = useState<readonly File[]>([]);
  const [judged, setJudged] = useState(false);
  const [judgement, setJudgement] = useState<JudgementDraft>(EMPTY_JUDGEMENT);
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [partial, setPartial] = useState<string | null>(null);
  const entityCode = period.entity.code;

  const judgementProblems = judged ? judgementErrors(judgement) : null;
  const errors = {
    reason: reason === null ? t("close.reopen.reasonError") : null,
    comment: reasonError(comment),
    contract: judgementProblems?.contract ?? null,
    conclusion: judgementProblems?.conclusion ?? null,
    rationale: judgementProblems?.rationale ?? null,
  };

  const attach = async (requestId: string): Promise<number> => {
    let unsaved = 0;
    for (const file of files) {
      try {
        const stored = await uploadFile(keys, ATTACHMENT_PURPOSE, file);
        const attached = await sendStep(keys, "POST", ATTACHMENTS_PATH, {
          file_object_id: stored.id,
          subject_type: "approval_request",
          subject_id: requestId,
          description: null,
        });
        if (!attached.ok) {
          unsaved += 1;
        }
      } catch {
        unsaved += 1;
      }
    }
    return unsaved;
  };

  const judge = async (): Promise<ApiProblem | null> => {
    if (!judged || judgement.contractId === null) {
      return null;
    }
    const outcome = await recordJudgement(keys, judgement);
    return outcome.ok ? null : outcome.problem;
  };

  const submit = async () => {
    setAttempted(true);
    if (reason === null || Object.values(errors).some((value) => value !== null)) {
      return;
    }
    setSubmitting(true);
    setProblem(null);
    setPartial(null);
    try {
      const created = await sendStep<{ readonly approval_request_id: string }>(
        keys,
        "POST",
        periodCommandPath(period.id, "request-reopen"),
        { reason_code: reason, comment: comment.trim() } satisfies PeriodReopenRequestIn,
        rowIfMatch(period.row_version),
      );
      if (!created.ok) {
        setProblem(created.problem);
        return;
      }
      const requestId = created.data.approval_request_id;
      await queryClient.invalidateQueries({ queryKey: EVERY_PERIOD });
      const unsaved = await attach(requestId);
      const judgementProblem = await judge();
      if (unsaved > 0 || judgementProblem !== null) {
        if (unsaved > 0) {
          const approval = await fetchApproval(requestId).catch(() => null);
          setPartial(
            t("close.reopen.partial", {
              count: unsaved,
              request: approval?.request_no ?? requestId,
            }),
          );
        }
        setProblem(judgementProblem);
        return;
      }
      keys.clear();
      toast.show({
        tone: "positive",
        message: t("close.reopen.done", { entity: entityCode, period: periodLabel }),
        action: canViewRequest
          ? {
              label: t("close.reopen.viewRequest"),
              onAction: () => void navigate(`/approvals/requests/${requestId}`),
            }
          : undefined,
      });
      onClose();
    } catch {
      // No answer to the request or to the judgement record: the drawer keeps its input.
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };

  const lock = period.current_lock;
  return (
    <Drawer
      open
      title={t("close.reopen.title", { period: periodLabel })}
      subtitle={
        lock === null
          ? `${entityCode} · ${bookLabel}`
          : t("close.reopen.subtitle", {
              entity: entityCode,
              book: bookLabel,
              at: formatTimestamp(lock.created_at),
            })
      }
      dirty={comment !== "" || files.length > 0 || judged}
      submitting={submitting}
      initialFocus="field"
      banner={
        partial === null && problem === null ? undefined : (
          <div className="flex flex-col gap-2">
            {partial === null ? null : <Banner tone="warning" title={partial} announce="live" />}
            <RefusalBanner problem={problem} />
          </div>
        )
      }
      primaryAction={{ label: t("close.reopen.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-05-drawer-reopen"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Banner
          tone="info"
          announce="static"
          title={t("close.reopen.info", { period: periodLabel })}
        />
        <SelectField
          name="reopen-reason"
          label={t("close.reopen.reason")}
          options={REASONS.map((value) => ({
            value,
            label: t(`close.reopen.reasonCode.${value}`),
          }))}
          value={reason}
          onChange={setReason}
          error={attempted ? errors.reason : null}
        />
        <ReasonField
          name="reopen-comment"
          label={t("close.reopen.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
        {canAttach ? (
          <EvidenceField
            name="reopen-attachments"
            label={t("close.reopen.attachments")}
            files={files}
            onChange={setFiles}
          />
        ) : null}
        {canJudge ? (
          <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              checked={judged}
              onChange={(event) => {
                setJudged(event.target.checked);
              }}
              className="size-4"
            />
            {t("close.reopen.judgement")}
          </label>
        ) : (
          // Supervisor ruling R-100 (a): not a dead end for a requester who records no judgement.
          <p className="text-body-sm text-fg-2">
            {t("close.reopen.judgementElsewhere")}{" "}
            {judgementRegisterHref === null ? null : (
              <Link to={judgementRegisterHref} className="text-accent-fg hover:underline">
                {t("close.reopen.judgementRegister")}
              </Link>
            )}
          </p>
        )}
        {judged ? (
          <fieldset className="flex flex-col gap-3 border-s border-hairline ps-4">
            <legend className="text-title-sm text-fg-1">{t("close.reopen.judgementLegend")}</legend>
            <JudgementFields
              entityCode={entityCode}
              namePrefix="reopen"
              draft={judgement}
              onChange={setJudgement}
              errors={attempted ? judgementProblems : null}
            />
          </fieldset>
        ) : null}
      </form>
    </Drawer>
  );
}

export interface ReopenRequestBannerProps {
  /** The pending `PERIOD_REOPEN` request whose subject is the period. */
  readonly request: PeriodApproval;
  readonly viewerId: string;
  /** SF-12:request is built, so the banner may link the request. */
  readonly canView: boolean;
}

/**
 * SCREENS_B §1.1 banner of a pending reopen request with its dual-approval status: "Dual approval ·
 * <n> of 2 recorded", each decision's approver, "on behalf of <delegator>" when delegated, and the UTC
 * time; "Review in Approvals", where approvers decide (J-14.2, J-14.3). The requester reads that two
 * others must review it and may withdraw the request (`POST /approvals/{id}/withdraw`). The banner
 * names the reason the request was submitted with (rev 1.93; API-S-Approval `reason_code`, 04 rev
 * 1.252, item APR-REQUEST-REASON-1) by the label the drawer offers; a reader the API withholds the
 * code from, and a code this build has no label for, read the sentence without it (rev 1.32).
 */
export function ReopenRequestBanner({ request, viewerId, canView }: ReopenRequestBannerProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const withdraw = useApprovalCommand(request.id, "withdraw");
  const [confirming, setConfirming] = useState(false);
  const step =
    request.steps.find((item) => item.step_no === request.current_step_no) ?? request.steps[0];
  const decisions = step?.decisions ?? [];
  const requester = request.preparer.id === viewerId;
  const reason = REASONS.find((value) => value === request.reason_code) ?? null;
  const said = {
    name: request.preparer.display_name,
    date: formatDate(timestampDate(request.submitted_at)),
    recorded: decisions.length,
    required: step?.min_approvers ?? decisions.length,
  };

  const send = async () => {
    const outcome = await withdraw.submit({ comment: null } satisfies ApprovalWithdrawIn);
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      setConfirming(false);
      await queryClient.invalidateQueries({ queryKey: EVERY_PERIOD });
      toast.show({ tone: "positive", message: t("close.cockpit.reopenRequest.withdraw.done") });
    }
  };

  return (
    <div data-testid="SF-05-banner-reopen-request">
      <Banner
        tone="info"
        announce="static"
        title={
          reason === null
            ? t("close.cockpit.banner.reopenRequest", said)
            : t("close.cockpit.banner.reopenRequestReason", {
                ...said,
                reason: t(`close.reopen.reasonCode.${reason}`),
              })
        }
        actions={
          canView || requester ? (
            <>
              {canView ? (
                <Link
                  to={`/approvals/requests/${request.id}`}
                  className="text-body-sm text-accent-fg hover:underline"
                >
                  {t("close.cockpit.reopenRequest.review")}
                </Link>
              ) : null}
              {requester ? (
                <Button
                  variant="link"
                  onClick={() => {
                    withdraw.reset();
                    setConfirming(true);
                  }}
                >
                  {t("approvals.withdraw")}
                </Button>
              ) : null}
            </>
          ) : undefined
        }
      >
        {decisions.length === 0 ? null : (
          <ul className="flex flex-col gap-0.5">
            {decisions.map((decision) => (
              <li key={decision.id} className="flex flex-wrap gap-x-2">
                <span>{decision.approver.display_name}</span>
                {decision.on_behalf_of === null ? null : (
                  <span>
                    {t("approvals.request.onBehalfOf", {
                      name: decision.on_behalf_of.display_name,
                    })}
                  </span>
                )}
                <span data-volatile="" className="num text-fg-2">
                  {formatTimestamp(decision.decided_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
        {requester ? <p>{t("close.cockpit.reopenRequest.requester")}</p> : null}
      </Banner>
      <Modal
        open={confirming}
        variant="confirmation"
        title={t("close.cockpit.reopenRequest.withdraw.title")}
        description={t("close.cockpit.reopenRequest.withdraw.description")}
        primaryAction={{
          label: t("approvals.withdraw"),
          onAction: () => void send(),
        }}
        submitting={withdraw.pending}
        onClose={() => setConfirming(false)}
      >
        <RefusalBanner problem={withdraw.problem} />
      </Modal>
    </div>
  );
}
