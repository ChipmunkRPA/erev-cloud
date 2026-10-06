// About dialog (SCREENS_B §11.5 SF-27; D-61, D-75; DESIGN_SYSTEM DS-BR-02, DS-BR-05, DS-BR-06). Opened by
// the Help menu item "About eRev Cloud" or the search parameter `dialog=about` (SCREENS §0.4, OQ-S-10):
// the wordmark, "by Chipmunk Robotics", the product name, the engine release of `GET /me`
// (`engine_release`, 04 §16.12), the licence links and the copyright. Focus moves to the title; Esc or
// Close removes the parameter, and focus returns to the element that opened the dialog.
import { useCallback, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router";

import { Skeleton } from "../../components/feedback/Skeleton";
import { X } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { type EngineRelease, useMe } from "../../lib/api/queries/me";
import { t } from "../../lib/i18n/t";

export const DIALOG_PARAM = "dialog";
export const ABOUT_DIALOG = "about";
export const LICENSE_PATH = "/licenses/LICENSE.txt";
export const NOTICE_PATH = "/licenses/NOTICE.txt";
const BUILD_SHA_LENGTH = 8;

/** `Engine <engine_version> · build <first 8 of build_sha> · schema <schema_revision>`. */
export function engineLine(release: EngineRelease | null | undefined): string {
  if (release === null || release === undefined) {
    return t("shell.about.releaseUnavailable");
  }
  return t("shell.about.engine", {
    version: release.engine_version,
    build: release.build_sha.slice(0, BUILD_SHA_LENGTH),
    schema: release.schema_revision,
  });
}

export function AboutDialog() {
  const [params, setParams] = useSearchParams();
  const close = useCallback(() => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete(DIALOG_PARAM);
        return next;
      },
      { replace: true },
    );
  }, [setParams]);
  if (params.get(DIALOG_PARAM) !== ABOUT_DIALOG) {
    return null;
  }
  return createPortal(<AboutPanel onClose={close} />, document.body);
}

function AboutPanel({ onClose }: { readonly onClose: () => void }) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const me = useMe();
  useModalFocus({ panel, initialFocus: title });

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  const wordmark = t("shell.wordmark");
  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="SF-27-page"
        className="flex max-h-full w-[var(--modal-w-sm)] max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <div className="flex items-start justify-between gap-2 px-5 pt-5">
          <h2 ref={title} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
            {t("shell.about.title")}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            icon={X}
            aria-label={t("common.dialog.close")}
            onClick={onClose}
          />
        </div>
        <div className="flex flex-col gap-1 px-5 pt-4">
          {/* DS-BR-02: live text, not an image; DS-BR-05: the byline only here. */}
          <span role="img" aria-label={wordmark} className="text-title-lg text-fg-1">
            {wordmark}
          </span>
          <p className="text-body-sm text-fg-3">{t("shell.about.byline")}</p>
          <p className="pt-3 text-body font-medium text-fg-1">{t("shell.productName")}</p>
          {me.isPending ? (
            <Skeleton region={t("shell.about.releaseRegion")} count={1} />
          ) : (
            <p
              data-testid="SF-27-engine-release"
              data-volatile=""
              className="font-mono text-mono text-fg-2"
            >
              {engineLine(me.data?.engine_release)}
            </p>
          )}
          <p className="pt-3 text-body-sm">
            <a href={LICENSE_PATH} className="text-accent-fg hover:underline">
              {t("shell.about.licence")}
            </a>
            <span aria-hidden="true" className="px-1.5 text-fg-3">
              ·
            </span>
            <a href={NOTICE_PATH} className="text-accent-fg hover:underline">
              {t("shell.about.notices")}
            </a>
          </p>
          <p className="text-body-sm text-fg-2">{t("shell.about.copyright")}</p>
        </div>
        <div className="flex justify-end px-5 py-4">
          <Button variant="secondary" onClick={onClose}>
            {t("common.dialog.close")}
          </Button>
        </div>
      </div>
    </div>
  );
}
