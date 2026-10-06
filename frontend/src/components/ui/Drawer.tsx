// Drawer (DESIGN_SYSTEM DS-CMP-09). The modal variant (scrim, focus trap; APG Dialog (Modal)) holds
// create and edit forms: closing a dirty form asks "Discard changes?" through a confirmation modal, and
// focus returns to the trigger. The footer holds "Cancel", an optional secondary action such as "Save
// draft", then the primary action. The docked variant (Explain, column chooser) is a normal region
// without scrim or trap that closes with Esc while focus is inside it. A drawer never opens another
// drawer; at most one modal sits above it.
import { type ReactNode, type RefObject, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { t } from "../../lib/i18n/t";
import { X } from "../icons/registry";
import { Button } from "./Button";
import { cn } from "./cn";
import { trapTab, useModalFocus } from "./dialog";
import { Modal, type ModalAction } from "./Modal";

export type DrawerVariant = "modal" | "docked";

export interface DrawerProps {
  readonly open: boolean;
  readonly title: string;
  /** An optional subtitle or identifier under the title. */
  readonly subtitle?: string | undefined;
  readonly variant?: DrawerVariant;
  /** `--drawer-w-wide` instead of `--drawer-w`. */
  readonly wide?: boolean;
  /** The form holds unsaved changes: closing asks for confirmation first. */
  readonly dirty?: boolean;
  /** While submitting the drawer does not close. */
  readonly submitting?: boolean;
  /** `field`: focus the first field on open (forms); `title`: informational drawers. */
  readonly initialFocus?: "field" | "title";
  /** A DS-CMP-29 banner at the top of the body, for a server error. */
  readonly banner?: ReactNode;
  /** The footer's primary action; "Cancel" precedes it. */
  readonly primaryAction?: ModalAction | undefined;
  /** A second action between "Cancel" and the primary action, for example "Save draft". */
  readonly secondaryAction?: ModalAction | undefined;
  readonly onClose: () => void;
  readonly children: ReactNode;
}

export function Drawer(props: DrawerProps) {
  if (!props.open) {
    return null;
  }
  if ((props.variant ?? "modal") === "docked") {
    return <DockedDrawer {...props} />;
  }
  return createPortal(<ModalDrawer {...props} />, document.body);
}

/** The close request with the dirty check; returns the confirmation modal to render. */
function useCloseRequest({ dirty = false, submitting = false, onClose }: DrawerProps) {
  const [confirming, setConfirming] = useState(false);
  const requestClose = () => {
    if (submitting) {
      return;
    }
    if (dirty) {
      setConfirming(true);
    } else {
      onClose();
    }
  };
  const confirmation = (
    <Modal
      open={confirming}
      variant="confirmation"
      title={t("common.dialog.discard.title")}
      description={t("common.dialog.discard.description")}
      primaryAction={{
        label: t("common.dialog.discard.confirm"),
        destructive: true,
        onAction: () => {
          setConfirming(false);
          onClose();
        },
      }}
      onClose={() => setConfirming(false)}
    />
  );
  return { requestClose, confirmation };
}

function useEscape(
  panel: RefObject<HTMLElement | null>,
  requestClose: () => void,
  trap: boolean,
): void {
  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        requestClose();
      } else if (trap) {
        trapTab(event, root);
      }
    };
    root.addEventListener("keydown", onKeyDown);
    return () => root.removeEventListener("keydown", onKeyDown);
  }, [panel, requestClose, trap]);
}

interface DrawerContentProps extends DrawerProps {
  readonly titleId: string;
  readonly titleRef: RefObject<HTMLHeadingElement | null>;
  readonly requestClose: () => void;
}

function DrawerContent({
  title,
  subtitle,
  banner,
  primaryAction,
  secondaryAction,
  submitting = false,
  children,
  titleId,
  titleRef,
  requestClose,
}: DrawerContentProps) {
  return (
    <>
      <div className="flex items-start gap-3 border-b border-hairline px-[var(--panel-pad)] py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 ref={titleRef} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
            {title}
          </h2>
          {subtitle === undefined ? null : <p className="text-body-sm text-fg-2">{subtitle}</p>}
        </div>
        <Button
          variant="ghost"
          size="sm"
          icon={X}
          aria-label={t("common.dialog.close")}
          onClick={requestClose}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-[var(--panel-pad)]">
        {banner}
        {children}
      </div>
      {primaryAction === undefined ? null : (
        <div className="flex justify-end gap-2 border-t border-hairline px-[var(--panel-pad)] py-3">
          <Button variant="secondary" onClick={requestClose}>
            {t("common.dialog.cancel")}
          </Button>
          {secondaryAction === undefined ? null : (
            <Button
              variant="secondary"
              type={secondaryAction.form === undefined ? "button" : "submit"}
              form={secondaryAction.form}
              disabledReason={
                submitting ? t("common.dialog.submitting") : secondaryAction.disabledReason
              }
              onClick={secondaryAction.onAction}
            >
              {secondaryAction.label}
            </Button>
          )}
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
      )}
    </>
  );
}

function ModalDrawer(props: DrawerProps) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const { requestClose, confirmation } = useCloseRequest(props);
  useModalFocus({ panel, initialFocus: props.initialFocus === "title" ? titleRef : undefined });
  useEscape(panel, requestClose, true);
  return (
    <>
      <div className="fixed inset-0 z-[var(--z-drawer)] flex justify-end bg-scrim">
        <div
          ref={panel}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          className={cn(
            "flex h-full max-w-full flex-col border-s border-hairline bg-raised shadow-overlay",
            props.wide === true ? "w-[var(--drawer-w-wide)]" : "w-[var(--drawer-w)]",
          )}
        >
          <DrawerContent
            {...props}
            titleId={titleId}
            titleRef={titleRef}
            requestClose={requestClose}
          />
        </div>
      </div>
      {confirmation}
    </>
  );
}

function DockedDrawer(props: DrawerProps) {
  const titleId = useId();
  const panel = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const { requestClose, confirmation } = useCloseRequest(props);
  useEscape(panel, requestClose, false);
  return (
    <>
      <aside
        ref={panel}
        aria-labelledby={titleId}
        className={cn(
          "flex h-full max-w-full shrink-0 flex-col border-s border-hairline bg-raised",
          props.wide === true ? "w-[var(--drawer-w-wide)]" : "w-[var(--drawer-w)]",
        )}
      >
        <DrawerContent
          {...props}
          titleId={titleId}
          titleRef={titleRef}
          requestClose={requestClose}
        />
      </aside>
      {confirmation}
    </>
  );
}
