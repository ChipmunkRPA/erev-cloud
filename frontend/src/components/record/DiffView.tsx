// Approval diff view (DESIGN_SYSTEM DS-CMP-16; REQ-UX-012): the maker-checker review surface. The
// request header, the segregation-of-duties notice, the justification, the impact strip, the diff body
// and the decision form. The field diff table is captioned "Proposed changes (<n>)"; every changed row
// has a marker glyph and a visually hidden prefix, so tints never carry the meaning alone. `N` and
// `Shift+N` move between changes outside text fields. Buttons never submit on `Mod Enter`: an approval is
// a deliberate press. A stale request and a viewer without approval rights get no decision form. The field
// diff table and the change navigation are exported for records that show a diff outside an approval (the
// audit event drawer, SCREENS_B §6.3), with their own caption.
import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

import { isTypingTarget } from "../../lib/a11y/typing";
import { formatTimestamp, MINUS_SIGN, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Banner } from "../feedback/Banner";
import { fieldId } from "../form/Field";
import { ReasonField, reasonError } from "../form/ReasonField";
import { Switch } from "../form/Switch";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Modal } from "../ui/Modal";
import { StatusChip } from "../ui/StatusChip";

export type ChangeKind = "added" | "removed" | "changed" | "unchanged";

export interface FieldChange {
  readonly id: string;
  readonly field: string;
  readonly kind: ChangeKind;
  /** Formatted display values; null shows the no-value dash. */
  readonly current: string | null;
  readonly proposed: string | null;
  /** The DS-FMT-31 delta of a changed numeric field, formatted. */
  readonly delta?: string | undefined;
}

export interface RoutingStep {
  readonly id: string;
  /** For example "Controller approval · 1 of 1". */
  readonly label: string;
  readonly approver?: string | undefined;
  /** The RFC 3339 UTC instant of the recorded decision. */
  readonly at?: string | undefined;
  readonly comment?: string | undefined;
}

export type RequestStatus = "Pending approval" | "Approved" | "Rejected" | "Withdrawn" | "Stale";
export type Decision = "approve" | "reject";

export interface DiffViewProps {
  readonly requestId: string;
  /** For example "Revenue policy change" or "Period reopen". */
  readonly requestType: string;
  readonly status: RequestStatus;
  readonly maker: string;
  /** The RFC 3339 UTC instant the maker submitted the request. */
  readonly submittedAt: string;
  readonly routing?: readonly RoutingStep[];
  /** The viewer submitted the request or recorded an earlier approval step. */
  readonly viewerIsMaker?: boolean;
  readonly canApprove: boolean;
  readonly justification?: string | undefined;
  /** The DS-CMP-06 impact strip from the dry run. */
  readonly impact?: ReactNode;
  /** The field diff of configuration and single records. */
  readonly changes?: readonly FieldChange[];
  /** The grid diff of tabular subjects, shown instead of the field diff. */
  readonly grid?: ReactNode;
  readonly submitting?: boolean;
  readonly onDecide?: ((decision: Decision, comment: string) => void) | undefined;
}

const MARKER: Readonly<Record<Exclude<ChangeKind, "unchanged">, string>> = {
  removed: MINUS_SIGN,
  added: "+",
  changed: "~",
};

const COMMENT_FIELD = "approvalComment";

function Value({ text, struck }: { readonly text: string | null; readonly struck: boolean }) {
  return <span className={cn(struck && "text-fg-2 line-through")}>{text ?? NO_VALUE}</span>;
}

export interface FieldDiffProps {
  readonly changes: readonly FieldChange[];
  /** The table caption of `count` changes; the approval diff reads "Proposed changes (<n>)". */
  readonly caption?: ((count: number) => string) | undefined;
}

export function FieldDiff({ changes, caption }: FieldDiffProps) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  const changed = changes.filter((change) => change.kind !== "unchanged");
  const hasUnchanged = changed.length < changes.length;
  const hasDelta = changes.some((change) => change.delta !== undefined);
  const shown = showUnchanged ? changes : changed;
  return (
    <div className="flex flex-col gap-2">
      {hasUnchanged ? (
        <Switch
          label={t("common.diff.showUnchanged")}
          checked={showUnchanged}
          onChange={setShowUnchanged}
        />
      ) : null}
      <table className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-body-sm font-semibold text-fg-1">
          {caption === undefined
            ? t("common.diff.caption", { count: changed.length })
            : caption(changed.length)}
        </caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className="w-16 px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.change")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.field")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.current")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.proposed")}
            </th>
            {hasDelta ? (
              <th scope="col" className="px-2 py-1.5 text-end font-medium">
                {t("common.diff.column.delta")}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {shown.map((change) => (
            <tr
              key={change.id}
              data-change={change.kind}
              tabIndex={change.kind === "unchanged" ? undefined : -1}
              className={cn(
                "border-b border-hairline align-top",
                change.kind === "removed" && "bg-diff-removed-bg",
                change.kind === "added" && "bg-diff-added-bg",
              )}
            >
              <td className="px-2 py-1.5">
                {change.kind === "unchanged" ? null : (
                  <>
                    <span aria-hidden="true" className="num font-medium text-fg-1">
                      {MARKER[change.kind]}
                    </span>
                    <span className="sr-only">{t(`common.diff.prefix.${change.kind}`)}</span>
                  </>
                )}
              </td>
              <th scope="row" className="px-2 py-1.5 text-start font-medium text-fg-1">
                {change.field}
              </th>
              <td className={cn("px-2 py-1.5", change.kind === "changed" && "bg-diff-removed-bg")}>
                <Value
                  text={change.current}
                  struck={change.kind === "removed" || change.kind === "changed"}
                />
              </td>
              <td className={cn("px-2 py-1.5", change.kind === "changed" && "bg-diff-added-bg")}>
                <Value text={change.proposed} struck={false} />
              </td>
              {hasDelta ? <td className="num px-2 py-1.5 text-end">{change.delta ?? ""}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionForm({
  submitting,
  onDecide,
}: {
  readonly submitting: boolean;
  readonly onDecide: (decision: Decision, comment: string) => void;
}) {
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const decide = (decision: Decision) => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      document.getElementById(fieldId(COMMENT_FIELD))?.focus();
      return;
    }
    if (decision === "reject") {
      setConfirming(true);
    } else {
      onDecide("approve", comment.trim());
    }
  };

  return (
    <div className="sticky bottom-0 flex flex-col gap-3 border-t border-hairline bg-surface py-3">
      <ReasonField
        name={COMMENT_FIELD}
        label={t("common.diff.comment")}
        value={comment}
        onChange={setComment}
        showError={attempted}
      />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => decide("reject")}>
          {t("common.diff.reject")}
        </Button>
        <Button variant="primary" loading={submitting} onClick={() => decide("approve")}>
          {t("common.diff.approve")}
        </Button>
      </div>
      <Modal
        open={confirming}
        variant="confirmation"
        title={t("common.diff.rejectTitle")}
        description={t("common.diff.rejectDescription")}
        primaryAction={{
          label: t("common.diff.reject"),
          destructive: true,
          onAction: () => {
            setConfirming(false);
            onDecide("reject", comment.trim());
          },
        }}
        onClose={() => setConfirming(false)}
      />
    </div>
  );
}

/**
 * `N` and `Shift+N` move between the changed rows under `root` while focus is not in a field and no
 * modal is open (DS-CMP-16).
 */
export function useChangeNavigation(root: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const element = root.current;
      if (
        element === null ||
        (event.key !== "n" && event.key !== "N") ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.defaultPrevented ||
        isTypingTarget(event.target) ||
        document.querySelector("[aria-modal='true']") !== null
      ) {
        return;
      }
      const rows = Array.from(element.querySelectorAll<HTMLElement>("tr[tabindex='-1']"));
      if (rows.length === 0) {
        return;
      }
      event.preventDefault();
      const index = rows.findIndex((row) => row.contains(document.activeElement));
      const next = event.shiftKey
        ? index === -1
          ? rows.length - 1
          : Math.max(index - 1, 0)
        : Math.min(index + 1, rows.length - 1);
      rows[next]?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [root]);
}

export function DiffView({
  requestId,
  requestType,
  status,
  maker,
  submittedAt,
  routing = [],
  viewerIsMaker = false,
  canApprove,
  justification,
  impact,
  changes = [],
  grid,
  submitting = false,
  onDecide,
}: DiffViewProps) {
  const root = useRef<HTMLDivElement>(null);
  useChangeNavigation(root);

  const pending = status === "Pending approval";
  return (
    <div ref={root} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-mono-sm text-fg-2">{requestId}</span>
          <span className="text-title-sm text-fg-1">{requestType}</span>
          <StatusChip status={status} />
        </div>
        <p className="text-body-sm text-fg-2">
          {t("common.diff.submitted", { maker, at: formatTimestamp(submittedAt) })}
        </p>
        {routing.length === 0 ? null : (
          <ol className="flex flex-col gap-1 text-body-sm">
            {routing.map((step) => (
              <li key={step.id} className="flex flex-wrap gap-x-2 text-fg-2">
                <span className="text-fg-1">{step.label}</span>
                {step.approver === undefined ? null : <span>{step.approver}</span>}
                {step.at === undefined ? null : <span>{formatTimestamp(step.at)}</span>}
                {step.comment === undefined ? null : <q className="text-fg-2">{step.comment}</q>}
              </li>
            ))}
          </ol>
        )}
      </div>
      {status === "Stale" ? (
        <Banner tone="warning" title={t("common.diff.stale")} announce="static" headingLevel={3} />
      ) : null}
      {pending && viewerIsMaker ? (
        <Banner tone="info" title={t("common.diff.sod")} announce="static" headingLevel={3} />
      ) : null}
      {justification === undefined ? null : (
        <blockquote className="border-s-2 border-default ps-3 text-body text-fg-1">
          {justification}
        </blockquote>
      )}
      {impact}
      {grid ?? <FieldDiff changes={changes} />}
      {!pending || viewerIsMaker ? null : canApprove && onDecide !== undefined ? (
        <DecisionForm submitting={submitting} onDecide={onDecide} />
      ) : (
        <p className="text-body-sm text-fg-2">{t("common.diff.noRights")}</p>
      )}
    </div>
  );
}

export interface InlineDiffProps {
  readonly field: string;
  readonly current: string;
  readonly proposed: string;
}

/** The inline variant for timelines: "End date: 31 Dec 2026 → 30 Jun 2027". */
export function InlineDiff({ field, current, proposed }: InlineDiffProps) {
  return (
    <span className="text-body-sm text-fg-2">
      <span aria-hidden="true">{`${field}: ${current} → ${proposed}`}</span>
      <span className="sr-only">{t("common.diff.inline", { field, current, proposed })}</span>
    </span>
  );
}
