// Record header (DESIGN_SYSTEM DS-CMP-06; SCREENS §4.1): breadcrumb, title row (identifier with its
// copy button, the page h1, status chips, actions), meta row, banner slot, tracker and KPI strip, inside
// `section aria-labelledby=<h1 id>`. Once the KPI strip scrolls out of view a 48 px sticky condensed
// header appears at the top of the scroll container; its title is an aria-hidden `p`, so the full
// header stays the accessible one. The compact variant (obligation pane) has no breadcrumb and a
// title-md h2.
import { type ReactNode, type Ref, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { t } from "../../lib/i18n/t";
import { useToast } from "../feedback/Toast";
import { CopySimple } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";

export interface Crumb {
  readonly label: string;
  readonly to: string;
}

export interface MetaItem {
  readonly label: string;
  readonly value: ReactNode;
}

export interface RecordIdentifier {
  readonly value: string;
  /** The copy button name, for example "Copy contract id"; none renders no copy button. */
  readonly copyLabel?: string | undefined;
  /** The toast after copying, for example "Copied NS-SO-DE-5004.". */
  readonly copiedMessage?: string | undefined;
  /** SCREENS SCR-TID-04 `identifier`, for example "SF-03-identifier". */
  readonly testId?: string | undefined;
}

export interface RecordHeaderProps {
  readonly title: string;
  readonly variant?: "page" | "compact";
  /** Ancestor links; the identifier, when given, is the current crumb. */
  readonly breadcrumb?: readonly Crumb[];
  readonly identifier?: RecordIdentifier | undefined;
  /** Status chips (DS-CMP-19), including the neutral version chip. */
  readonly chips?: ReactNode;
  /** Secondary actions, one primary action and the overflow menu, in that order. */
  readonly actions?: ReactNode;
  /** The primary action again, for the condensed header. */
  readonly primaryAction?: ReactNode;
  readonly meta?: readonly MetaItem[];
  /** Stale, pending approval, locked and error banners. */
  readonly banner?: ReactNode;
  /** The five-step tracker (DS-CMP-17), contracts only. */
  readonly tracker?: ReactNode;
  readonly kpis?: ReactNode;
  readonly headingRef?: Ref<HTMLHeadingElement>;
}

function useCondensed(sentinel: React.RefObject<HTMLDivElement | null>, enabled: boolean): boolean {
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    const target = sentinel.current;
    if (!enabled || target === null || typeof IntersectionObserver === "undefined") {
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry !== undefined) {
        const top = entry.rootBounds?.top ?? 0;
        setCondensed(!entry.isIntersecting && entry.boundingClientRect.top < top);
      }
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [sentinel, enabled]);
  return condensed;
}

export function RecordHeader({
  title,
  variant = "page",
  breadcrumb,
  identifier,
  chips,
  actions,
  primaryAction,
  meta,
  banner,
  tracker,
  kpis,
  headingRef,
}: RecordHeaderProps) {
  const titleId = useId();
  const toast = useToast();
  const sentinel = useRef<HTMLDivElement>(null);
  const page = variant === "page";
  const condensed = useCondensed(sentinel, page && kpis !== undefined);
  const Heading = page ? "h1" : "h2";

  const copy = (value: RecordIdentifier) => {
    void navigator.clipboard
      .writeText(value.value)
      .then(() => toast.show({ tone: "neutral", message: value.copiedMessage ?? value.value }));
  };

  return (
    <>
      {condensed ? (
        <div className="sticky top-0 z-[var(--z-sticky)] h-0">
          <div className="absolute inset-x-0 top-0 flex h-12 items-center gap-3 border-b border-hairline bg-surface px-[var(--gutter)]">
            <p aria-hidden="true" className="flex min-w-0 items-center gap-2">
              {identifier === undefined ? null : (
                <span className="font-mono text-mono-sm text-fg-3">{identifier.value}</span>
              )}
              <span className="truncate text-title-sm text-fg-1">{title}</span>
            </p>
            <span aria-hidden="true" className="flex items-center gap-1.5">
              {chips}
            </span>
            <span className="ms-auto flex items-center">{primaryAction}</span>
          </div>
        </div>
      ) : null}
      <section
        aria-labelledby={titleId}
        className={cn(
          "flex flex-col border-b border-hairline bg-surface",
          page ? "gap-3 px-[var(--gutter)] py-[var(--panel-pad)]" : "gap-2 p-[var(--panel-pad)]",
        )}
      >
        {page && breadcrumb !== undefined ? (
          <nav aria-label={t("common.record.breadcrumb")}>
            <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
              {breadcrumb.map((crumb) => (
                <li key={crumb.to} className="flex items-center gap-1.5">
                  <Link to={crumb.to} className="hover:text-fg-1 hover:underline">
                    {crumb.label}
                  </Link>
                  <span aria-hidden="true">/</span>
                </li>
              ))}
              {identifier === undefined ? null : <li aria-current="page">{identifier.value}</li>}
            </ol>
          </nav>
        ) : null}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {identifier === undefined ? null : (
            <span data-testid={identifier.testId} className="flex items-center gap-1">
              <span className="font-mono text-mono text-fg-2">{identifier.value}</span>
              {identifier.copyLabel === undefined ? null : (
                <Button
                  variant="ghost"
                  size="sm"
                  icon={CopySimple}
                  aria-label={identifier.copyLabel}
                  onClick={() => copy(identifier)}
                />
              )}
            </span>
          )}
          <Heading
            ref={headingRef}
            id={titleId}
            tabIndex={-1}
            className={cn("text-fg-1", page ? "text-title-lg" : "text-title-md")}
          >
            {title}
          </Heading>
          {chips === undefined ? null : <span className="flex items-center gap-1.5">{chips}</span>}
          {actions === undefined ? null : (
            <span className="ms-auto flex items-center gap-2">{actions}</span>
          )}
        </div>
        {meta === undefined || meta.length === 0 ? null : (
          <dl className="flex flex-wrap gap-x-6 gap-y-1">
            {meta.map((item) => (
              <div key={item.label} className="flex items-baseline gap-1.5">
                <dt className="text-caption text-fg-3">{item.label}</dt>
                <dd className="text-body-sm text-fg-1">{item.value}</dd>
              </div>
            ))}
          </dl>
        )}
        {banner}
        {tracker}
        {kpis}
        <div ref={sentinel} aria-hidden="true" className="h-0" />
      </section>
    </>
  );
}
