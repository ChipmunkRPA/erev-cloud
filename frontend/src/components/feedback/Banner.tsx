// Banner (DESIGN_SYSTEM DS-CMP-29). A banner present on load is a static element with a heading; a
// banner inserted after load is a live region: role "status" for info, positive and warning, "alert"
// for negative. Only non-blocking info banners can be dismissed.
import type { ReactNode, Ref } from "react";

import { t } from "../../lib/i18n/t";
import { CheckCircle, type Icon, Info, WarningCircle, X, XCircle } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";

export type BannerTone = "info" | "positive" | "warning" | "negative";

export interface BannerProps {
  readonly tone: BannerTone;
  readonly title: string;
  readonly children?: ReactNode;
  /** Link-button actions, for example "Retry". */
  readonly actions?: ReactNode;
  /** `static`: rendered with the page; `live`: inserted after load and announced by its role. */
  readonly announce?: "live" | "static";
  readonly headingLevel?: 2 | 3 | 4;
  /** The global region above the page: square corners. */
  readonly global?: boolean;
  readonly onDismiss?: () => void;
  readonly titleRef?: Ref<HTMLHeadingElement>;
}

const TONE_ICON: Readonly<Record<BannerTone, Icon>> = {
  info: Info,
  positive: CheckCircle,
  warning: WarningCircle,
  negative: XCircle,
};

const TONE_CLASS: Readonly<Record<BannerTone, string>> = {
  info: "bg-info-bg border-info-border",
  positive: "bg-positive-bg border-positive-border",
  warning: "bg-warning-bg border-warning-border",
  negative: "bg-negative-bg border-negative-border",
};

const ICON_CLASS: Readonly<Record<BannerTone, string>> = {
  info: "text-info-fg",
  positive: "text-positive-fg",
  warning: "text-warning-fg",
  negative: "text-negative-fg",
};

export function Banner({
  tone,
  title,
  children,
  actions,
  announce = "live",
  headingLevel = 2,
  global = false,
  onDismiss,
  titleRef,
}: BannerProps) {
  const ToneIcon = TONE_ICON[tone];
  const role = announce === "static" ? undefined : tone === "negative" ? "alert" : "status";
  const Heading = `h${String(headingLevel)}` as "h2" | "h3" | "h4";
  const dismissible = onDismiss !== undefined && tone === "info";
  return (
    <div
      role={role}
      data-tone={tone}
      className={cn(
        "flex items-start gap-2 border px-3 py-2.5",
        global ? "rounded-none" : "rounded-md",
        TONE_CLASS[tone],
      )}
    >
      <ToneIcon aria-hidden="true" className={cn("mt-0.5 shrink-0", ICON_CLASS[tone])} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <Heading ref={titleRef} tabIndex={-1} className="text-body-sm font-semibold text-fg-1">
          {title}
        </Heading>
        {children === undefined ? null : <div className="text-body-sm text-fg-1">{children}</div>}
        {actions === undefined ? null : <div className="mt-1 flex flex-wrap gap-3">{actions}</div>}
      </div>
      {dismissible ? (
        <Button
          variant="ghost"
          size="sm"
          icon={X}
          aria-label={t("common.banner.dismiss")}
          onClick={onDismiss}
        />
      ) : null}
    </div>
  );
}
