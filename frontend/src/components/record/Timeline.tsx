// Timeline and activity (DESIGN_SYSTEM DS-CMP-12): `ol aria-label="Activity"` grouped under UTC date
// headings (DS-FMT-16); each event has an aria-hidden icon on the connector, the actor, a verb phrase,
// the object link and `time datetime=<ISO 8601 UTC>` with seconds (DS-FMT-17), then an optional inline
// diff, comment and evidence links. "Load older activity" pages; there is no infinite scroll and no
// live region. The audit variant header links to the chain verification or shows the failure banner.
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";

import { formatDate, formatNumber, formatTimestamp, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Banner } from "../feedback/Banner";
import { Skeleton } from "../feedback/Skeleton";
import { type Icon, Paperclip, ShieldCheck } from "../icons/registry";
import { Button } from "../ui/Button";

export interface TimelineEvent {
  readonly id: string;
  /** The RFC 3339 UTC instant of the event. */
  readonly at: string;
  readonly icon: Icon;
  /** A person's name, "System", "Import batch B-2026-0042" or "Proposal accepted by <name>". */
  readonly actor: string;
  /** People get a 20 px initials avatar. */
  readonly actorIsPerson?: boolean;
  /** The verb phrase, for example "changed End date"; it names the event type in text. */
  readonly verb: string;
  readonly object?: { readonly label: string; readonly to: string } | undefined;
  /** An inline diff (DS-CMP-16 inline variant). */
  readonly diff?: ReactNode;
  readonly comment?: string | undefined;
  readonly attachments?: readonly { readonly label: string; readonly href: string }[];
}

export type AuditChainState =
  | { readonly verifiedAt: string; readonly to: string }
  | { readonly failedAtEvent: number; readonly to: string };

export interface TimelineProps {
  readonly events: readonly TimelineEvent[];
  readonly status?: "loading" | "error" | "ready";
  /** DS-CMP-29 error banner with Retry. */
  readonly errorState?: ReactNode;
  /** The audit variant header. */
  readonly auditChain?: AuditChainState | undefined;
  /** Event-type chips and the "Show system events" switch. */
  readonly filters?: ReactNode;
  readonly hasOlder?: boolean;
  readonly loadingOlder?: boolean;
  readonly onLoadOlder?: (() => void) | undefined;
  /** Record activity: the comment composer posts with the button or `Mod Enter`. */
  readonly onPostComment?: ((text: string) => void) | undefined;
  readonly headingLevel?: 2 | 3 | 4;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter((part) => part !== "")
    .slice(0, 2)
    .map((part) => part.charAt(0).toLocaleUpperCase())
    .join("");
}

function AuditHeader({ state }: { readonly state: AuditChainState }) {
  if ("failedAtEvent" in state) {
    return (
      <Banner
        tone="negative"
        announce="static"
        headingLevel={3}
        title={t("common.timeline.auditFailed", {
          event: formatNumber(state.failedAtEvent, { kind: "count" }),
        })}
        actions={
          <Link to={state.to} className="text-body-sm text-accent-fg hover:underline">
            {t("common.timeline.auditDetails")}
          </Link>
        }
      />
    );
  }
  return (
    <Link
      to={state.to}
      className="inline-flex items-center gap-1.5 self-start text-body-sm text-fg-2 hover:text-fg-1 hover:underline"
    >
      <ShieldCheck aria-hidden="true" className="shrink-0 text-positive-fg" />
      {t("common.timeline.auditVerified", { timestamp: formatTimestamp(state.verifiedAt) })}
    </Link>
  );
}

function Composer({ onPost }: { readonly onPost: (text: string) => void }) {
  const id = useId();
  const [text, setText] = useState("");
  const post = () => {
    if (text.trim() !== "") {
      onPost(text);
      setText("");
    }
  };
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-body-sm font-medium text-fg-1">
        {t("common.timeline.comment")}
      </label>
      <textarea
        id={id}
        value={text}
        rows={3}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            post();
          }
        }}
        className="rounded-md border border-control bg-surface px-3 py-2 text-body text-fg-1"
      />
      <Button variant="secondary" className="self-end" onClick={post}>
        {t("common.timeline.postComment")}
      </Button>
    </div>
  );
}

function EventItem({
  event,
  dateHeading,
  headingLevel,
}: {
  readonly event: TimelineEvent;
  readonly dateHeading: string | null;
  readonly headingLevel: 2 | 3 | 4;
}) {
  const EventIcon = event.icon;
  const Heading = `h${String(headingLevel)}` as "h2" | "h3" | "h4";
  return (
    <li className="flex flex-col">
      {dateHeading === null ? null : (
        <Heading className="pb-2 pt-3 text-caption text-fg-3">{dateHeading}</Heading>
      )}
      <div className="flex gap-3">
        <span className="relative flex w-5 shrink-0 justify-center">
          <span aria-hidden="true" className="absolute inset-y-0 w-px bg-default" />
          <EventIcon
            aria-hidden="true"
            size={20}
            className="relative shrink-0 bg-surface text-fg-2"
          />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5 pb-4">
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-body-sm text-fg-1">
            {event.actorIsPerson === true ? (
              <span
                aria-hidden="true"
                className="inline-flex size-5 items-center justify-center rounded-full bg-active text-caption text-fg-2"
              >
                {initials(event.actor)}
              </span>
            ) : null}
            <span className="font-medium">{event.actor}</span> <span>{event.verb}</span>
            {event.object === undefined ? null : (
              <>
                {" "}
                <Link to={event.object.to} className="text-accent-fg hover:underline">
                  {event.object.label}
                </Link>
              </>
            )}
          </p>
          <time dateTime={event.at} className="num text-caption text-fg-3">
            {formatTimestamp(event.at, { seconds: true })}
          </time>
          {event.diff}
          {event.comment === undefined ? null : (
            <blockquote className="rounded-md bg-subtle px-3 py-2 text-body-sm text-fg-1">
              {event.comment}
            </blockquote>
          )}
          {event.attachments === undefined || event.attachments.length === 0 ? null : (
            <ul className="flex flex-wrap gap-3">
              {event.attachments.map((attachment) => (
                <li key={attachment.href}>
                  <a
                    href={attachment.href}
                    className="inline-flex items-center gap-1 text-body-sm text-accent-fg hover:underline"
                  >
                    <Paperclip aria-hidden="true" className="shrink-0" />
                    {attachment.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </li>
  );
}

export function Timeline({
  events,
  status = "ready",
  errorState,
  auditChain,
  filters,
  hasOlder = false,
  loadingOlder = false,
  onLoadOlder,
  onPostComment,
  headingLevel = 3,
}: TimelineProps) {
  let body: ReactNode;
  if (status === "loading") {
    body = <Skeleton region={t("common.timeline.activity")} count={3} />;
  } else if (status === "error") {
    body = errorState;
  } else if (events.length === 0) {
    body = <p className="text-body-sm text-fg-2">{t("common.timeline.empty")}</p>;
  } else {
    let previousDate: string | null = null;
    body = (
      <ol aria-label={t("common.timeline.activity")} className="flex flex-col">
        {events.map((event) => {
          const date = timestampDate(event.at);
          const dateHeading = date === previousDate ? null : formatDate(date);
          previousDate = date;
          return (
            <EventItem
              key={event.id}
              event={event}
              dateHeading={dateHeading}
              headingLevel={headingLevel}
            />
          );
        })}
      </ol>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {auditChain === undefined ? null : <AuditHeader state={auditChain} />}
      {filters}
      {onPostComment === undefined ? null : <Composer onPost={onPostComment} />}
      {body}
      {hasOlder && status === "ready" ? (
        <Button
          variant="secondary"
          className="self-start"
          loading={loadingOlder}
          onClick={onLoadOlder}
        >
          {t("common.timeline.loadOlder")}
        </Button>
      ) : null}
    </div>
  );
}
