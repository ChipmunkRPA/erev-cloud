// Modal (DESIGN_SYSTEM DS-CMP-11; APG Dialog (Modal)). A confirmation is an alertdialog whose initial
// focus is the least destructive action ("Cancel"); a form focuses its first field. Tab is trapped,
// Esc closes unless submitting, and focus returns to the trigger. Success is reported with a toast,
// never a modal.
import { type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { t } from "../../lib/i18n/t";
import { Button } from "./Button";
import { cn } from "./cn";
import { trapTab, useModalFocus } from "./dialog";

export type ModalVariant = "confirmation" | "form" | "diff";

export interface ModalAction {
  readonly label: string;
  readonly onAction?: (() => void) | undefined;
  /** Destructive commands use the Danger button. */
  readonly destructive?: boolean;
  /** The id of the form this action submits. */
  readonly form?: string | undefined;
  readonly disabledReason?: string | undefined;
}

export interface ModalProps {
  readonly open: boolean;
  readonly variant: ModalVariant;
  readonly title: string;
  /** The consequence text, referenced by aria-describedby. */
  readonly description?: string | undefined;
  readonly primaryAction: ModalAction;
  readonly cancelLabel?: string | undefined;
  readonly submitting?: boolean;
  readonly onClose: () => void;
  readonly children?: ReactNode;
  /** SCREENS SCR-TID-04 `dialog-<name>` of the dialog, for example "SF-11-dialog-dismiss". */
  readonly testId?: string | undefined;
}

const WIDTH: Readonly<Record<ModalVariant, string>> = {
  confirmation: "w-[var(--modal-w-sm)]",
  form: "w-[var(--modal-w-md)]",
  diff: "w-[var(--modal-w-lg)]",
};

export function Modal(props: ModalProps) {
  if (!props.open) {
    return null;
  }
  return createPortal(<ModalPanel {...props} />, document.body);
}

function ModalPanel({
  variant,
  title,
  description,
  primaryAction,
  cancelLabel,
  submitting = false,
  onClose,
  children,
  testId,
}: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useModalFocus({ panel, initialFocus: variant === "confirmation" ? cancel : undefined });

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!submitting) {
          onClose();
        }
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => root.removeEventListener("keydown", onKeyDown);
  }, [submitting, onClose]);

  const waiting = submitting ? t("common.dialog.submitting") : undefined;
  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role={variant === "confirmation" ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        data-testid={testId}
        tabIndex={-1}
        className={cn(
          "flex max-h-full max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay",
          WIDTH[variant],
        )}
      >
        <div className="flex flex-col gap-1 px-5 pt-5">
          <h2 id={titleId} className="text-title-md text-fg-1">
            {title}
          </h2>
          {description === undefined ? null : (
            <p id={descriptionId} className="text-body-sm text-fg-2">
              {description}
            </p>
          )}
        </div>
        {children === undefined ? null : (
          <div className="min-h-0 overflow-y-auto px-5 pt-4">{children}</div>
        )}
        <div className="flex justify-end gap-2 px-5 py-4">
          <Button ref={cancel} variant="secondary" disabledReason={waiting} onClick={onClose}>
            {cancelLabel ?? t("common.dialog.cancel")}
          </Button>
          <Button
            variant={primaryAction.destructive === true ? "danger" : "primary"}
            type={primaryAction.form === undefined ? "button" : "submit"}
            form={primaryAction.form}
            loading={submitting}
            disabledReason={primaryAction.disabledReason}
            onClick={primaryAction.onAction}
          >
            {primaryAction.label}
          </Button>
        </div>
      </div>
    </div>
  );
}
