// SF-09:audit-log event drawer (SCREENS_B §6.3 "Event drawer"; SCREENS SCR-URL-12, SCR-URL-32 `event`;
// DESIGN_SYSTEM DS-CMP-09 docked panel, DS-CMP-16 field diff, DS-CMP-19, DS-FMT-17, DS-FMT-22, DS-FMT-23;
// 04 T-PLT-19; docs/dev-guide.md DG-KRN-AUD-05; BUILD_SPEC RPS-21). The docked panel "Event <sequence>":
// the action with its outcome chip and the instant with seconds; the actor with role codes, the sign-in
// method and MFA; the object by its type in words, linked where its record has a screen that opens from
// the id; the table "Changes (<n>)" of the changed fields only, from the event's `diff` (`{path, before,
// after}` of each changed leaf) or, for a creation or a removal, from the leaves of the one document;
// the comment; the detail as JSON; and the recorded values of the chain. Values are shown as recorded:
// the API redacts credential keys to "[REDACTED]". The event names the actor and the principal a system
// step acted for (API-S-Actor, 04 §16.14; SCREENS_B rev 1.45); the API client and the support grant are
// ids, so they appear among the recorded values in the DS-FMT-23 form and never in place of a name.
// Since SCREENS_B rev 1.57 the object reads by its business label (`object_label`), the actor links to
// the user screen for a holder of `user.manage` (`actor_membership_id`), and a member that is null
// before and null after is no change.
import { type ReactNode, useRef } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { CopySimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { type FieldChange, FieldDiff, useChangeNavigation } from "../../components/record/DiffView";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Drawer } from "../../components/ui/Drawer";
import { StatusChip, type StatusWord } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import { announce } from "../../lib/a11y/announce";
import type { Access } from "../../lib/access";
import {
  type AuditEvent,
  type AuditOutcome,
  isNamedObject,
  objectRoute,
} from "../../lib/api/queries/audit";
import { USER_MANAGE_PERMISSION, USER_ROUTE, userRoute } from "../../lib/api/queries/users";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { hashPrefix } from "../reports/viewer/RunStamp";
import { recordedText } from "./chain";

/** The audit object type of an approval request (04 T-PLT-19 `object_type`). */
const APPROVAL_OBJECT = "approval_request";

/** SCREENS_B §6.3 "Outcome": E-81 `audit_outcome` as DS-CMP-19 chips, in the order the filter offers. */
export const OUTCOME_CHIPS: Readonly<Record<AuditOutcome, StatusWord>> = {
  SUCCESS: "Succeeded",
  DENIED: "Denied",
  FAILED: "Failed",
};

export function OutcomeChip({ outcome }: { readonly outcome: AuditOutcome }) {
  return <StatusChip status={OUTCOME_CHIPS[outcome]} />;
}

/**
 * SCREENS_B §6.3 "Actor" (rev 1.45): a person by display name, the system by name, an API client by
 * its name and an operator as "Operator <name> under support grant". API-S-Actor carries the name of
 * every kind (04 §16.14), so no id stands for one.
 */
export function actorName(actor: AuditEvent["actor"]): string {
  switch (actor.kind) {
    case "SYSTEM":
      return t("evidence.auditLog.actor.system");
    case "OPERATOR":
      return t("evidence.auditLog.actor.operator", { name: actor.display_name });
    case "API_CLIENT":
    case "USER":
      return actor.display_name;
  }
}

/** The object type in words: `import_upload` reads "Import upload" (T-PLT-19 stores the table name). */
export function objectTypeLabel(objectType: string): string {
  const words = objectType.replaceAll("_", " ").trim();
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The leaves of a recorded document by dotted path, in the order DG-KRN-AUD-05 walks them. */
function leaves(
  document: Readonly<Record<string, unknown>>,
  prefix = "",
): readonly (readonly [string, unknown])[] {
  return Object.keys(document)
    .sort()
    .flatMap((key) => {
      const path = prefix === "" ? key : `${prefix}.${key}`;
      const member = document[key];
      return isRecord(member) && Object.keys(member).length > 0
        ? leaves(member, path)
        : [[path, member] as const];
    });
}

/** A member the record does not hold: null and an absent member read alike. */
function unset(value: unknown): boolean {
  return value === null || value === undefined;
}

function change(index: number, path: string, before: unknown, after: unknown): FieldChange {
  let kind: FieldChange["kind"] = "changed";
  if (unset(before)) {
    kind = "added";
  } else if (unset(after)) {
    kind = "removed";
  }
  return {
    id: `${String(index)}:${path}`,
    field: path,
    kind,
    current: recordedText(before),
    proposed: recordedText(after),
  };
}

/**
 * The changed fields of an event (SCREENS_B §6.3; REQ-PLT-018). An update carries `diff`, the changed
 * leaves of `before` against `after`; a creation carries `after` alone and a removal `before` alone, so
 * every leaf of that document that holds a value is a change. Unchanged fields never appear, and a
 * member that is null before and null after is no change (rev 1.57): nothing was added or removed.
 */
export function eventChanges(
  event: Pick<AuditEvent, "before" | "after" | "diff">,
): readonly FieldChange[] {
  if (Array.isArray(event.diff)) {
    return event.diff.flatMap((entry, index) =>
      typeof entry.path === "string" && !(unset(entry.before) && unset(entry.after))
        ? [change(index, entry.path, entry.before, entry.after)]
        : [],
    );
  }
  if (event.before !== null && event.after !== null) {
    const before = new Map(leaves(event.before));
    const after = new Map(leaves(event.after));
    return [...new Set([...before.keys(), ...after.keys()])]
      .sort()
      .filter(
        (path) =>
          !(unset(before.get(path)) && unset(after.get(path))) &&
          JSON.stringify(before.get(path)) !== JSON.stringify(after.get(path)),
      )
      .map((path, index) => change(index, path, before.get(path), after.get(path)));
  }
  if (event.after !== null) {
    return leaves(event.after)
      .filter(([, value]) => !unset(value))
      .map(([path, value], index) => change(index, path, null, value));
  }
  if (event.before !== null) {
    return leaves(event.before)
      .filter(([, value]) => !unset(value))
      .map(([path, value], index) => change(index, path, value, null));
  }
  return [];
}

export interface ObjectLinkProps {
  readonly objectType: string;
  readonly objectId: string | null;
  /** The business identifier of the object (API-S-AuditEvent `object_label`), or null. */
  readonly label: string | null;
  readonly built: ReadonlySet<string>;
  readonly access: Access;
  /** Inside a grid cell the link leaves the Tab order (DS-CMP-10 roving tabindex). */
  readonly inGrid?: boolean;
  /** What an object without a label and without a screen shows: nothing, or its type in words. */
  readonly unlinked?: "none" | "words";
}

const LINK = "truncate text-accent-fg hover:text-accent-fg-hover hover:underline";
const IDENTIFIER = "font-mono text-mono-sm";

/**
 * SCREENS_B §6.3 "Object" (rev 1.57): the business label of the object as the event carries it — an
 * identifier in the identifier face, a name in the text face — linked to the record's screen where
 * that screen opens from the id. An event without a label — a type the API labels none, an event
 * without an object id, a row that is gone or that the reader's access does not show — keeps the type
 * in words, linked where the type has a screen; nothing says whether a label exists.
 */
export function ObjectLink({
  objectType,
  objectId,
  label,
  built,
  access,
  inGrid = false,
  unlinked = "none",
}: ObjectLinkProps) {
  const to = objectRoute(objectType, objectId, built, access);
  const face = label !== null && !isNamedObject(objectType) ? IDENTIFIER : undefined;
  if (to === null) {
    if (label !== null) {
      return (
        <span className={cn("truncate text-fg-1", face)} title={label}>
          {label}
        </span>
      );
    }
    return unlinked === "words" ? objectTypeLabel(objectType) : <NoValue />;
  }
  return (
    <Link
      to={to}
      tabIndex={inGrid ? -1 : undefined}
      title={label ?? undefined}
      className={cn(LINK, face)}
    >
      {label ?? objectTypeLabel(objectType)}
    </Link>
  );
}

/**
 * SF-14:user of the person who acted (SCREENS RT-108), for a holder of `user.manage` when the event
 * carries the membership (04 API-R-10: null for the system, an API client, an operator and a removed
 * member); else null.
 */
export function actorRoute(
  event: Pick<AuditEvent, "actor_membership_id">,
  built: ReadonlySet<string>,
  access: Access,
): string | null {
  return event.actor_membership_id !== null &&
    access.holdsAnywhere(USER_MANAGE_PERMISSION) &&
    built.has(USER_ROUTE)
    ? userRoute(event.actor_membership_id)
    : null;
}

export interface ActorNameProps {
  readonly event: Pick<AuditEvent, "actor" | "actor_membership_id">;
  readonly built: ReadonlySet<string>;
  readonly access: Access;
  readonly inGrid?: boolean;
}

/** SCREENS_B §6.3 "Actor": the name, linked to the user screen where the viewer may open it. */
export function ActorName({ event, built, access, inGrid = false }: ActorNameProps) {
  const name = actorName(event.actor);
  const to = actorRoute(event, built, access);
  return to === null ? (
    <span className="truncate" title={name}>
      {name}
    </span>
  ) : (
    <Link to={to} tabIndex={inGrid ? -1 : undefined} title={name} className={LINK}>
      {name}
    </Link>
  );
}

/** DS-FMT-23: a system id or a hash as its first 8 and last 4 characters, with the full value and copy. */
function SystemValue({ value, name }: { readonly value: string; readonly name: string }) {
  return (
    <span className="inline-flex items-center gap-1" data-volatile="">
      <Tooltip content={value}>
        {(trigger) => (
          <span
            {...trigger}
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
            tabIndex={0}
            className="font-mono text-mono-sm text-fg-1"
          >
            {hashPrefix(value)}
          </span>
        )}
      </Tooltip>
      <Button
        variant="ghost"
        size="sm"
        icon={CopySimple}
        aria-label={t("evidence.auditLog.record.copy", { name })}
        onClick={() => {
          void navigator.clipboard
            .writeText(value)
            .then(() => announce(t("evidence.auditLog.record.copied", { name }), "polite"));
        }}
      />
    </span>
  );
}

function Definition({ term, children }: { readonly term: string; readonly children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-3">{term}</dt>
      <dd className="min-w-0 break-words text-fg-1">{children}</dd>
    </>
  );
}

function mono(text: string): ReactNode {
  return <span className="font-mono text-mono-sm text-fg-1">{text}</span>;
}

const LIST = "grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-body-sm";
const HEADING = "text-body-sm font-semibold text-fg-1";

export interface EventDrawerProps {
  /** The chain sequence the drawer is open on. */
  readonly sequence: number;
  /** The event of that sequence; undefined while it is read alone (SCREENS_B §6.3 rev 1.57). */
  readonly event: AuditEvent | undefined;
  /** The title of the problem when that read failed; null otherwise. */
  readonly error?: string | null;
  readonly onRetry?: (() => void) | undefined;
  readonly built: ReadonlySet<string>;
  readonly access: Access;
  readonly onClose: () => void;
}

/**
 * The docked panel "Event <sequence>". It opens at once: an event the loaded rows hold fills it
 * directly, another is read alone by its sequence and the panel shows the loading state, or the
 * failure of that read with "Retry", until the event arrives.
 */
export function EventDrawer({
  sequence,
  event,
  error = null,
  onRetry,
  built,
  access,
  onClose,
}: EventDrawerProps) {
  const title = t("evidence.auditLog.drawer.title", {
    sequence: formatNumber(sequence, { kind: "count" }),
  });
  let body: ReactNode = null;
  if (event !== undefined) {
    body = <EventBody event={event} built={built} access={access} />;
  } else if (error === null) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  }
  return (
    <div data-testid="SF-09-drawer-event" className="flex h-full">
      <Drawer
        open
        variant="docked"
        title={title}
        onClose={onClose}
        banner={
          event !== undefined || error === null ? undefined : (
            <Banner
              tone="negative"
              title={t("evidence.auditLog.drawer.loadError")}
              actions={
                onRetry === undefined ? undefined : (
                  <Button variant="link" onClick={onRetry}>
                    {t("evidence.auditLog.retry")}
                  </Button>
                )
              }
            >
              {error}
            </Banner>
          )
        }
      >
        {body}
      </Drawer>
    </div>
  );
}

interface EventBodyProps {
  readonly event: AuditEvent;
  readonly built: ReadonlySet<string>;
  readonly access: Access;
}

function EventBody({ event, built, access }: EventBodyProps) {
  const diff = useRef<HTMLDivElement>(null);
  // DS-CMP-16: `N` and `Shift+N` move between the changes.
  useChangeNavigation(diff);
  const changes = eventChanges(event);
  const ids: readonly (readonly [string, string | null])[] = [
    [t("evidence.auditLog.record.eventId"), event.id],
    [t("evidence.auditLog.record.objectId"), event.object_id],
    // API-S-Actor since 04 rev 1.139: the name is shown after the actor, the recorded id stays here.
    [t("evidence.auditLog.record.onBehalfOf"), event.on_behalf_of?.id ?? null],
    [t("evidence.auditLog.record.apiClient"), event.api_client_id],
    [t("evidence.auditLog.record.supportGrant"), event.support_grant_id],
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <p className="flex flex-wrap items-center gap-2">
          {mono(event.action)}
          <OutcomeChip outcome={event.outcome} />
        </p>
        <time dateTime={event.occurred_at} data-volatile="" className="num text-body-sm text-fg-2">
          {formatTimestamp(event.occurred_at, { seconds: true })}
        </time>
      </div>

      <dl className={LIST}>
        <Definition term={t("evidence.auditLog.column.actor")}>
          <ActorName event={event} built={built} access={access} />
        </Definition>
        {event.actor_roles.length === 0 ? null : (
          <Definition term={t("evidence.auditLog.column.roles")}>
            {mono(event.actor_roles.join(", "))}
          </Definition>
        )}
        {event.auth_method === null ? null : (
          <Definition term={t("evidence.auditLog.drawer.signIn")}>
            {mono(event.auth_method)}
          </Definition>
        )}
        {event.mfa_verified === null ? null : (
          <Definition term={t("evidence.auditLog.column.mfa")}>
            {t(event.mfa_verified ? "common.grid.yes" : "common.grid.no")}
          </Definition>
        )}
        {event.on_behalf_of === null ? null : (
          <Definition term={t("evidence.auditLog.column.onBehalfOf")}>
            {actorName(event.on_behalf_of)}
          </Definition>
        )}
        <Definition term={t("evidence.auditLog.column.object")}>
          {event.object_label === null ? (
            <ObjectLink
              objectType={event.object_type}
              objectId={event.object_id}
              label={null}
              built={built}
              access={access}
              unlinked="words"
            />
          ) : (
            <span className="flex flex-wrap items-baseline gap-x-1.5">
              <span>{objectTypeLabel(event.object_type)}</span>
              <ObjectLink
                objectType={event.object_type}
                objectId={event.object_id}
                label={event.object_label}
                built={built}
                access={access}
              />
            </span>
          )}
        </Definition>
        {event.object_version === null ? null : (
          <Definition term={t("evidence.auditLog.drawer.objectVersion")}>
            {mono(event.object_version)}
          </Definition>
        )}
        {event.reason_code === null ? null : (
          <Definition term={t("evidence.auditLog.column.reason")}>
            {mono(event.reason_code)}
          </Definition>
        )}
        {event.approval_request_id === null ? null : (
          <Definition term={t("evidence.auditLog.drawer.approval")}>
            <ObjectLink
              objectType={APPROVAL_OBJECT}
              objectId={event.approval_request_id}
              label={null}
              built={built}
              access={access}
              unlinked="words"
            />
          </Definition>
        )}
      </dl>

      {changes.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("evidence.auditLog.drawer.noChanges")}</p>
      ) : (
        <div ref={diff} data-testid="SF-09-diff">
          <FieldDiff
            changes={changes}
            caption={(count) => t("evidence.auditLog.drawer.changes", { count })}
          />
        </div>
      )}

      {event.comment === null || event.comment === "" ? null : (
        <section className="flex flex-col gap-1.5">
          <h3 className={HEADING}>{t("evidence.auditLog.drawer.comment")}</h3>
          <blockquote className="rounded-md bg-subtle px-3 py-2 text-body-sm text-fg-1">
            {event.comment}
          </blockquote>
        </section>
      )}

      {Object.keys(event.detail).length === 0 ? null : (
        <section className="flex flex-col gap-1.5">
          <h3 className={HEADING}>{t("evidence.auditLog.drawer.detail")}</h3>
          {/* Wrapped, not scrolled: a scrolling region would need its own tab stop. */}
          <pre
            data-volatile=""
            className="whitespace-pre-wrap break-all rounded-md bg-subtle px-3 py-2 font-mono text-mono-sm text-fg-1"
          >
            {JSON.stringify(event.detail, null, 2)}
          </pre>
        </section>
      )}

      <section className="flex flex-col gap-1.5">
        <h3 className={HEADING}>{t("evidence.auditLog.record.title")}</h3>
        <dl className={LIST}>
          <Definition term={t("evidence.auditLog.record.hmac")}>
            <SystemValue value={event.hmac} name={t("evidence.auditLog.record.hmac")} />
          </Definition>
          <Definition term={t("evidence.auditLog.record.previousHmac")}>
            {event.prev_hmac === null ? (
              <NoValue />
            ) : (
              <SystemValue
                value={event.prev_hmac}
                name={t("evidence.auditLog.record.previousHmac")}
              />
            )}
          </Definition>
          <Definition term={t("evidence.auditLog.record.key")}>
            <span data-volatile="">{mono(event.hmac_key_id)}</span>
          </Definition>
          <Definition term={t("evidence.auditLog.column.requestId")}>
            <SystemValue value={event.request_id} name={t("evidence.auditLog.column.requestId")} />
          </Definition>
          {ids.map(([name, value]) =>
            value === null ? null : (
              <Definition key={name} term={name}>
                <SystemValue value={value} name={name} />
              </Definition>
            ),
          )}
          {event.source_ip === null ? null : (
            <Definition term={t("evidence.auditLog.record.sourceAddress")}>
              {mono(event.source_ip)}
            </Definition>
          )}
        </dl>
      </section>
    </div>
  );
}
