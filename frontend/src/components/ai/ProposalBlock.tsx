// AI proposal block (DESIGN_SYSTEM DS-COL-23, DS-CMP-25, DS-CPY-08; D-46). A `section` named by its
// "Proposed" header and described by the visually hidden note "AI-generated proposal. Not applied until
// accepted.". The dashed `--proposal-border` edge means not applied; an accepted block has a solid
// hairline edge and the chip "Accepted by <name>". "Accept" and "Edit and accept" render only for a
// proposal bound to a command and never while a figure is uncited; other proposals offer a copy action.
// Dismissing needs a reason. There is no accent colour, confidence percentage or automatic application.
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";

import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Skeleton } from "../feedback/Skeleton";
import { ReasonField, reasonError } from "../form/ReasonField";
import { CheckCircle, Sparkle, WarningCircle } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Modal } from "../ui/Modal";
import { ToneChip } from "../ui/StatusChip";

export type ProposalState = "generating" | "ready" | "accepted" | "dismissed" | "failed";

export interface ProposalCitation {
  readonly number: number;
  readonly label: string;
  /** A record route or a document page reference. */
  readonly to: string;
}

export interface ProposalBlockProps {
  readonly state: ProposalState;
  /** The source line, for example "Contract review · 07 Sep 2026 14:05 UTC". */
  readonly source: string;
  /** The proposal body: extracted fields, a narrative answer or an anomaly flag. */
  readonly children?: ReactNode;
  readonly citations?: readonly ProposalCitation[];
  /** The backend flagged an amount without a citation. */
  readonly uncitedFigure?: boolean;
  /** Only proposals bound to a command accept (contract review in 1.0). */
  readonly onAccept?: (() => void) | undefined;
  readonly onEditAndAccept?: (() => void) | undefined;
  /** The copy action of proposals without a command, for example "Copy answer". */
  readonly copy?: { readonly label: string; readonly onCopy: () => void } | undefined;
  readonly onDismiss?: ((reason: string) => void) | undefined;
  readonly onCancel?: (() => void) | undefined;
  readonly acceptedBy?: string | undefined;
  readonly dismissal?: { readonly by: string; readonly reason: string } | undefined;
  readonly headingLevel?: 2 | 3 | 4;
}

function DismissModal({
  open,
  onClose,
  onDismiss,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onDismiss: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  return (
    <Modal
      open={open}
      variant="form"
      title={t("ai.proposal.dismissTitle")}
      primaryAction={{
        label: t("ai.proposal.dismiss"),
        onAction: () => {
          setAttempted(true);
          if (reasonError(reason) === null) {
            onDismiss(reason.trim());
            onClose();
          }
        },
      }}
      onClose={onClose}
    >
      <ReasonField
        name="dismissReason"
        label={t("ai.proposal.dismissReason")}
        value={reason}
        onChange={setReason}
        showError={attempted}
      />
    </Modal>
  );
}

export function ProposalBlock({
  state,
  source,
  children,
  citations = [],
  uncitedFigure = false,
  onAccept,
  onEditAndAccept,
  copy,
  onDismiss,
  onCancel,
  acceptedBy,
  dismissal,
  headingLevel = 3,
}: ProposalBlockProps) {
  const headerId = useId();
  const noteId = useId();
  const [dismissing, setDismissing] = useState(false);
  const Heading = `h${String(headingLevel)}` as "h2" | "h3" | "h4";
  const accepted = state === "accepted";
  const actionable = state === "ready";

  return (
    <section
      aria-labelledby={headerId}
      aria-describedby={noteId}
      aria-busy={state === "generating" ? true : undefined}
      data-edge={accepted ? "solid" : "dashed"}
      className={cn(
        "flex flex-col gap-3 rounded-lg border bg-surface p-[var(--panel-pad)]",
        accepted ? "border-solid border-hairline" : "border-dashed border-proposal-border",
      )}
    >
      <span id={noteId} className="sr-only">
        {t("ai.proposal.note")}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        <Sparkle aria-hidden="true" size={16} className="shrink-0 text-fg-2" />
        <Heading id={headerId} className="text-caption font-medium text-fg-1">
          {t("ai.proposal.label")}
        </Heading>
        <span className="text-caption text-fg-3">{source}</span>
        {uncitedFigure && !accepted ? (
          <ToneChip tone="warning" icon={WarningCircle} label={t("ai.proposal.uncited")} />
        ) : null}
        {accepted && acceptedBy !== undefined ? (
          <ToneChip
            tone="positive"
            icon={CheckCircle}
            label={t("ai.proposal.acceptedBy", { name: acceptedBy })}
          />
        ) : null}
      </div>

      {state === "generating" ? (
        <div className="flex flex-col gap-2">
          <Skeleton region={t("ai.proposal.generating")} count={3} />
          <p className="text-body-sm text-fg-2">{t("ai.proposal.generating")}</p>
          {onCancel === undefined ? null : (
            <div>
              <Button size="sm" onClick={onCancel}>
                {t("ai.proposal.cancel")}
              </Button>
            </div>
          )}
        </div>
      ) : state === "failed" ? (
        <p className="text-body-sm text-fg-2">{t("ai.proposal.failed")}</p>
      ) : state === "dismissed" && dismissal !== undefined ? (
        <p className="text-body-sm text-fg-2">
          {t("ai.proposal.dismissedBy", { name: dismissal.by, reason: dismissal.reason })}
        </p>
      ) : (
        <>
          <div className="text-body text-fg-1">{children}</div>
          {citations.length === 0 ? null : (
            <div className="flex flex-col gap-1">
              <span className="text-caption text-fg-3">{t("ai.proposal.sources")}</span>
              <ol className="flex flex-col gap-0.5 text-body-sm">
                {citations.map((citation) => (
                  <li key={citation.number} className="flex gap-1.5">
                    <span className="num text-fg-3">{`[${formatNumber(citation.number)}]`}</span>
                    <Link to={citation.to} className="text-accent-fg hover:underline">
                      {citation.label}
                    </Link>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}

      {actionable ? (
        <div className="flex flex-wrap items-center gap-2">
          {onAccept === undefined || uncitedFigure ? null : (
            <Button variant="primary" size="sm" onClick={onAccept}>
              {t("ai.proposal.accept")}
            </Button>
          )}
          {onEditAndAccept === undefined || uncitedFigure ? null : (
            <Button size="sm" onClick={onEditAndAccept}>
              {t("ai.proposal.editAndAccept")}
            </Button>
          )}
          {copy === undefined ? null : (
            <Button size="sm" onClick={copy.onCopy}>
              {copy.label}
            </Button>
          )}
          {onDismiss === undefined ? null : (
            <>
              <Button variant="ghost" size="sm" onClick={() => setDismissing(true)}>
                {t("ai.proposal.dismiss")}
              </Button>
              <DismissModal
                open={dismissing}
                onClose={() => setDismissing(false)}
                onDismiss={onDismiss}
              />
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}
