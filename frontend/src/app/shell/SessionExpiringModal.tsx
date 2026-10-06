// Session expiry warning (SCREENS_B §12.4 X:session-expiring; SCREENS §1.1; DESIGN_SYSTEM DS-CMP-01
// states). Two minutes before `idle_expires_at` of API-S-Session (04 §16.12, T-PLT-08) a modal reads
// "Your session ends in 2 minutes." with the primary "Stay signed in", which reads `GET /session` again
// and so extends the idle expiry, and "Sign out". Esc stays signed in. A session already past its expiry
// shows nothing: the next request answers 401 and the client opens sign-in (DG-FE-04).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "../../components/ui/Button";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { queryKeys } from "../../lib/api/query-keys";
import { instantMs } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { fetchSession } from "../auth/RequireSession";
import { useShellSession } from "./SandboxIndicator";
import { useSignOut } from "./UserMenu";

/** DS-CMP-01: the warning opens two minutes before the idle expiry. */
export const SESSION_WARNING_MS = 120_000;
// setTimeout holds a signed 32-bit delay; a longer wait is scheduled again when it elapses.
const MAX_TIMER_MS = 2_147_483_647;

export function SessionExpiringModal() {
  const session = useShellSession();
  const idleExpiresAt = session?.authenticated === true ? session.idle_expires_at : null;
  // The expiry instant the warning was raised for; a new expiry from `GET /session` closes it.
  const [warnedFor, setWarnedFor] = useState<string | null>(null);

  useEffect(() => {
    if (idleExpiresAt === null) {
      return undefined;
    }
    const expires = instantMs(idleExpiresAt);
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = () => {
      const now = Date.now();
      if (now >= expires) {
        return;
      }
      const wait = expires - SESSION_WARNING_MS - now;
      if (wait <= 0) {
        setWarnedFor(idleExpiresAt);
        return;
      }
      timer = setTimeout(schedule, Math.min(wait, MAX_TIMER_MS));
    };
    schedule();
    return () => {
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, [idleExpiresAt]);

  if (idleExpiresAt === null || warnedFor !== idleExpiresAt) {
    return null;
  }
  return createPortal(
    <ExpiringPanel
      onDismiss={() => {
        setWarnedFor(null);
      }}
    />,
    document.body,
  );
}

function ExpiringPanel({ onDismiss }: { readonly onDismiss: () => void }) {
  const queryClient = useQueryClient();
  const signOut = useSignOut();
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const stay = useRef<HTMLButtonElement>(null);
  const [pending, setPending] = useState(false);
  useModalFocus({ panel, initialFocus: stay });

  const latest = useRef({ queryClient, onDismiss });
  useEffect(() => {
    latest.current = { queryClient, onDismiss };
  });

  const staySignedIn = async () => {
    setPending(true);
    try {
      await latest.current.queryClient.fetchQuery({
        queryKey: queryKeys.session(),
        queryFn: fetchSession,
        staleTime: 0,
      });
    } catch {
      // The warning stays open so the user can try again; a 401 has already opened sign-in.
      setPending(false);
      return;
    }
    setPending(false);
    latest.current.onDismiss();
  };

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        stay.current?.click();
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="flex w-[var(--modal-w-sm)] max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <h2 id={titleId} className="px-5 pt-5 text-title-md text-fg-1">
          {t("shell.session.expiring")}
        </h2>
        <div className="flex justify-end gap-2 px-5 py-4">
          <Button
            variant="secondary"
            onClick={() => {
              void signOut();
            }}
          >
            {t("shell.userMenu.signOut")}
          </Button>
          <Button
            ref={stay}
            variant="primary"
            loading={pending}
            onClick={() => {
              void staySignedIn();
            }}
          >
            {t("shell.session.staySignedIn")}
          </Button>
        </div>
      </div>
    </div>
  );
}
