// Toast (DESIGN_SYSTEM DS-CMP-22; DS-A11Y-22). Stacked at the bottom inline-end corner, at most three
// visible, newest last. Positive and neutral toasts without an action dismiss after 6 s and pause while
// hovered or focused; toasts with an action, and warning or negative toasts, stay until dismissed.
// Negative toasts are alerts, the others status messages. Focus never moves to a toast by itself:
// Alt+T focuses the newest toast and Esc returns focus to where it was.
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { t } from "../../lib/i18n/t";
import { CheckCircle, type Icon, Info, WarningCircle, X, XCircle } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";

export const TOAST_TIMEOUT_MS = 6_000;
export const MAX_VISIBLE_TOASTS = 3;

export type ToastTone = "neutral" | "positive" | "warning" | "negative";

export interface ToastInput {
  readonly tone: ToastTone;
  readonly message: string;
  readonly action?: { readonly label: string; readonly onAction: () => void } | undefined;
}

interface ToastRecord extends ToastInput {
  readonly id: number;
}

export interface ToastApi {
  readonly show: (toast: ToastInput) => number;
  readonly dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const value = useContext(ToastContext);
  if (value === null) {
    throw new Error("useToast needs ToastProvider");
  }
  return value;
}

/**
 * What a screen says when a command got no answer: its request, or its answer, was lost. The screen
 * stays as it is, and pressing again sends the command under the Idempotency-Key it had (DG-FE-05), so
 * a command that did take effect is not carried out twice.
 */
export function useNoAnswer(): () => void {
  const toast = useToast();
  return () => {
    toast.show({ tone: "negative", message: t("common.command.noAnswer") });
  };
}

const TONE_ICON: Readonly<Record<ToastTone, Icon>> = {
  neutral: Info,
  positive: CheckCircle,
  warning: WarningCircle,
  negative: XCircle,
};

const ICON_CLASS: Readonly<Record<ToastTone, string>> = {
  neutral: "text-fg-2",
  positive: "text-positive-fg",
  warning: "text-warning-fg",
  negative: "text-negative-fg",
};

interface ToastItemProps {
  readonly toast: ToastRecord;
  readonly onDismiss: (id: number) => void;
  readonly register: (id: number, element: HTMLDivElement | null) => void;
}

function ToastItem({ toast, onDismiss, register }: ToastItemProps) {
  const autoDismiss =
    (toast.tone === "positive" || toast.tone === "neutral") && toast.action === undefined;
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const remaining = useRef(TOAST_TIMEOUT_MS);

  useEffect(() => {
    if (!autoDismiss || hovered || focused) {
      return undefined;
    }
    const started = Date.now();
    const timer = setTimeout(() => onDismiss(toast.id), remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current -= Date.now() - started;
    };
  }, [autoDismiss, hovered, focused, onDismiss, toast.id]);

  const ToneIcon = TONE_ICON[toast.tone];
  return (
    <div
      ref={(element) => register(toast.id, element)}
      role={toast.tone === "negative" ? "alert" : "status"}
      tabIndex={-1}
      data-tone={toast.tone}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setFocused(false);
        }
      }}
      className="pointer-events-auto flex items-start gap-3 rounded-lg border border-hairline bg-raised p-3 shadow-popover"
    >
      <ToneIcon aria-hidden="true" className={cn("mt-0.5 shrink-0", ICON_CLASS[toast.tone])} />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
        <p className="line-clamp-2 text-body-sm text-fg-1">{toast.message}</p>
        {toast.action === undefined ? null : (
          <Button variant="link" onClick={toast.action.onAction}>
            {toast.action.label}
          </Button>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        icon={X}
        aria-label={t("common.toast.dismiss")}
        onClick={() => onDismiss(toast.id)}
      />
    </div>
  );
}

export function ToastProvider({ children }: { readonly children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly ToastRecord[]>([]);
  const nextId = useRef(1);
  const elements = useRef(new Map<number, HTMLDivElement>());
  const returnFocus = useRef<HTMLElement | null>(null);
  const region = useRef<HTMLElement>(null);
  const visible = toasts.slice(-MAX_VISIBLE_TOASTS);
  const newest = visible.at(-1)?.id;

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  const show = useCallback((toast: ToastInput) => {
    const id = nextId.current;
    nextId.current += 1;
    setToasts((current) => [...current, { ...toast, id }]);
    return id;
  }, []);
  const register = useCallback((id: number, element: HTMLDivElement | null) => {
    if (element === null) {
      elements.current.delete(id);
    } else {
      elements.current.set(id, element);
    }
  }, []);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (!event.altKey || event.code !== "KeyT" || newest === undefined) {
        return;
      }
      const element = elements.current.get(newest);
      if (element !== undefined) {
        event.preventDefault();
        if (
          !element.contains(document.activeElement) &&
          document.activeElement instanceof HTMLElement
        ) {
          returnFocus.current = document.activeElement;
        }
        element.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [newest]);

  // Esc inside the toast region returns focus to where Alt+T took it from.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const target = returnFocus.current;
      const inRegion =
        event.target instanceof Node && region.current?.contains(event.target) === true;
      if (event.key !== "Escape" || target === null || !inRegion) {
        return;
      }
      event.preventDefault();
      returnFocus.current = null;
      if (target.isConnected) {
        target.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <section
        aria-label={t("common.toast.region")}
        ref={region}
        className="pointer-events-none fixed bottom-4 end-4 z-[var(--z-toast)] flex w-90 flex-col gap-2"
      >
        {visible.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} register={register} />
        ))}
      </section>
    </ToastContext.Provider>
  );
}
