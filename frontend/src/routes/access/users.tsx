// SF-14 Users (SCREENS_B §9.10; SCREENS §0.4 RT-87, §0.3 SCR-IA-03, §0.7 SCR-PERM-01, SCR-ST-04, §0.8
// E-78; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-13, DS-CMP-19, DS-CMP-29; 04 API-R-05 `GET /users`,
// `POST /users`, API-R-06 `GET /roles`, API-R-07 `GET /sod-rules`, API-R-17 `GET /entities`; PRD ERR-22,
// BR-PLT-02; BS1-D-14; BUILD_SPEC WEB-19). The Settings frame with the Access route tabs, the `h1`
// "Users", the DataGrid "Members" (`GET /users?status&q&count=true`) with the Status chip and the search
// `q`, and "Invite user" for `user.manage`. The invite drawer takes Email, Display name and repeatable Role
// and Scope rows; a live SoD check over the chosen roles' permissions shows the ERR-22 alert with "Request
// an exception" focused (an exception needs the membership, so the invitation goes without the
// conflicting role first), and the answered invitation names its outcome: setup grants approved by rule
// AUTO-BOOTSTRAP while setup is incomplete, else a request waiting for approval. "Download access
// listing" is not rendered (BS1-D-14).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";
import { useLocation } from "react-router";

import { openMembership } from "../../app/shell/open-workspace";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import { placeProblemByEnd } from "../../lib/api/refusals";
import {
  permissionsOf,
  sodConflicts,
  useActiveRoles,
  useSodRules,
} from "../../lib/api/queries/roles";
import { entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import {
  currentRoles,
  EVERY_USER,
  fetchUsersPage,
  invitationOutcome,
  MEMBERSHIP_STATUSES,
  type MembershipStatus,
  scopeCodes,
  USER_MANAGE_PERMISSION,
  type UserInvite,
  type UserItem,
  type UserListQuery,
  userRoute,
  USERS_PATH,
  usersKey,
} from "../../lib/api/queries/users";
import {
  formatDate,
  formatNumber,
  formatTimestamp,
  NO_VALUE,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "../settings/index";
import {
  grantsValid,
  newGrantDraft,
  type RoleGrantDraft,
  RoleGrantRows,
  SodConflictBanner,
  toGrant,
} from "./role-fields";

function statusLabel(status: MembershipStatus): string {
  return chipFor("E-78", status)?.status ?? status;
}

/** SCREENS_B §9.10: the Status chip; the search `q` reaches the API as typed. */
export function userFilterFields(): readonly FilterField[] {
  return [
    {
      name: "status",
      label: t("access.users.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: MEMBERSHIP_STATUSES.map((status) => ({ value: status, label: statusLabel(status) })),
    },
  ];
}

/** The API query of the URL: `f.status` and `q`. */
export function userQuery(search: string, fields: readonly FilterField[]): UserListQuery {
  const parsed = parseFilters(search, fields);
  const status = parsed.filters.find((filter) => filter.field === "status");
  return { status: status?.values ?? [], q: parsed.query === "" ? null : parsed.query };
}

/** SCREENS_B §9.10 "Scope" of a member: "All entities" when any current role covers all, else the codes. */
export function memberScope(user: Pick<UserItem, "roles">): string {
  const roles = currentRoles(user);
  if (roles.length === 0) {
    return NO_VALUE;
  }
  if (roles.some((role) => role.is_all_entities)) {
    return t("access.users.scope.all");
  }
  const codes = new Set<string>();
  for (const role of roles) {
    for (const code of (scopeCodes(role) ?? "").split(", ")) {
      if (code !== "") {
        codes.add(code);
      }
    }
  }
  return [...codes].join(", ");
}

function RolesCell({ user }: { readonly user: UserItem }) {
  const roles = currentRoles(user);
  if (roles.length === 0) {
    return <span className="text-fg-3">{NO_VALUE}</span>;
  }
  return (
    <span className="flex flex-wrap items-center gap-1">
      {roles.map((role) => (
        <span key={role.assignment_id ?? role.role.id} className="flex items-center gap-1">
          <OutlineChip label={role.role.name} />
          {role.status === "REQUESTED" ? <StatusChip status="Pending approval" /> : null}
        </span>
      ))}
    </span>
  );
}

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

/**
 * SCREENS_B §9.10 (rev 1.105; 04 T-PLT-02 rev 1.316): an invited or a removed member's MFA state and last
 * sign-in are not shown to the workspace — API-S-User `sign_in_withheld`, with null in both members. The
 * two cells then read "Not shown", never "No" or "Never", which say of a member that there is no factor
 * and no sign-in.
 */
function notShown() {
  return <span className="text-fg-3">{t("access.users.notShown")}</span>;
}

/** SCREENS_B §9.10 "MFA": "Yes" or "No" of a member, "Not shown" of an invited or a removed one. */
function mfaText(user: Pick<UserItem, "mfa_enrolled" | "sign_in_withheld">): string {
  if (user.sign_in_withheld) {
    return t("access.users.notShown");
  }
  return t(user.mfa_enrolled === true ? "access.users.mfa.yes" : "access.users.mfa.no");
}

/** SCREENS_B §9.10 members grid columns. */
export function memberColumns(): readonly GridColumn<UserItem>[] {
  return [
    {
      id: "display_name",
      header: t("access.users.column.name"),
      kind: "identifier",
      value: (user) => user.display_name,
      href: (user) => userRoute(user.id),
      sortKey: "display_name",
      width: 200,
    },
    {
      id: "email",
      header: t("access.users.column.email"),
      kind: "text",
      value: (user) => user.email,
      render: (user) => mono(user.email),
      sortKey: "email",
      width: 224,
    },
    {
      id: "status",
      header: t("access.users.column.status"),
      kind: "status",
      value: (user) => user.status,
      render: (user) => <StatusChip status={statusLabel(user.status)} />,
    },
    {
      id: "roles",
      header: t("access.users.column.roles"),
      kind: "text",
      value: (user) =>
        currentRoles(user)
          .map((role) => role.role.name)
          .join("; "),
      render: (user) => <RolesCell user={user} />,
      width: 320,
    },
    {
      id: "scope",
      header: t("access.users.column.scope"),
      kind: "text",
      value: (user) => memberScope(user),
      width: 144,
    },
    {
      id: "mfa",
      header: t("access.users.column.mfa"),
      kind: "boolean",
      value: (user) => mfaText(user),
      // The cell is rendered here: the grid's own boolean cell prints "Yes" for the raw value
      // "true" alone, so it read "No" for every member, and it knows no third value.
      render: (user) => (user.sign_in_withheld ? notShown() : mfaText(user)),
      width: 112,
    },
    {
      id: "last_login_at",
      header: t("access.users.column.lastLogin"),
      kind: "timestamp",
      value: (user) => user.last_login_at,
      // A `render` is the whole cell: it answers the instant too, which it left empty.
      render: (user) => {
        if (user.sign_in_withheld) {
          return notShown();
        }
        return user.last_login_at === null ? (
          <span className="text-fg-3">{t("access.users.lastLogin.never")}</span>
        ) : (
          <span className="num">{formatTimestamp(user.last_login_at)}</span>
        );
      },
    },
    {
      id: "invited_at",
      header: t("access.users.column.invited"),
      kind: "text",
      value: (user) => user.invited_at,
      render: (user) => <span className="num">{formatDate(timestampDate(user.invited_at))}</span>,
      sortKey: "invited_at",
      width: 128,
    },
  ];
}

export function UsersList() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.users.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(USER_MANAGE_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.userManage"),
        })}
      />
    );
  } else {
    return <UsersPage me={me.data} />;
  }
  return (
    <div data-testid="SF-14-page" className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

function UsersPage({ me }: { readonly me: Me }) {
  const { search } = useLocation();
  const [inviting, setInviting] = useState(false);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const fields = useMemo(() => userFilterFields(), []);
  const query = userQuery(search, fields);
  const source: GridSource<UserItem> = {
    queryKey: usersKey(query),
    fetchPage: (cursor, sort) => fetchUsersPage(query, cursor, sort),
  };
  const columns = useMemo(() => memberColumns(), []);
  const title = t("access.users.title");
  const countLabel = (value: number) =>
    t("access.users.count", { count: value, formatted: formatNumber(value, { kind: "count" }) });

  return (
    <div
      data-testid="SF-14-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<UserItem>
          name="members"
          title={t("access.users.grid")}
          errorTitle={t("access.users.loadError")}
          countLabel={(value, formatted) => t("access.users.count", { count: value, formatted })}
          columns={columns}
          source={source}
          rowKey={(user) => user.id}
          rowLabel={(user) => user.display_name}
          rowHref={(user) => userRoute(user.id)}
          testIdPrefix="SF-14"
          rowTestKey={(user) => user.email}
          onTotalChange={(next) => setTotal(next?.count)}
          toolbarActions={
            <Button
              variant="primary"
              onClick={() => {
                setInviting(true);
              }}
            >
              {t("access.users.invite.title")}
            </Button>
          }
          filterBar={
            <FilterBar
              fields={fields}
              searchLabel={t("access.users.search")}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-14-filter-bar"
            />
          }
          emptyState={
            <EmptyState
              title={t("access.users.empty.title")}
              description={t("access.users.empty.description")}
            />
          }
          noResults={
            <EmptyState
              title={t("access.users.noResults.title")}
              description={t("access.users.noResults.description")}
            />
          }
        />
      </div>
      {inviting ? (
        <InviteDrawer
          me={me}
          onClose={() => {
            setInviting(false);
          }}
        />
      ) : null}
    </div>
  );
}

interface InviteDrawerProps {
  readonly me: Me;
  readonly onClose: () => void;
}

/**
 * docs/dev-guide.md DG-FE-06: the fields of "Invite user" and the pointers each shows the message of.
 * The body nests one row per role, and each row shows the two findings on its scope (04 T-PLT-10 writes
 * `roles[<n>].entity_codes`, the validation of the request `roles.<n>.entity_codes`). The role select
 * of a row shows none, and the entities of a row for all entities are not on screen: an error there is
 * the banner's.
 */
function inviteFields(
  drafts: readonly RoleGrantDraft[],
): Readonly<Record<string, readonly string[]>> {
  const fields: Record<string, readonly string[]> = { email: ["email"], name: ["display_name"] };
  drafts.forEach((draft, index) => {
    const row = String(index);
    // The entities of a row are on screen only while its scope is "Selected entities".
    fields[`entities:${row}`] = draft.allEntities
      ? []
      : [`roles[${row}].entity_codes`, `roles.${row}.entity_codes`];
    fields[`all:${row}`] = [`roles[${row}].is_all_entities`, `roles.${row}.is_all_entities`];
  });
  return fields;
}

/** SCREENS_B §9.10 "Invite user": Email, Display name and repeatable Role and Scope rows with the live SoD check. */
export function InviteDrawer({ me, onClose }: InviteDrawerProps) {
  // The workspace invited to is the session's: a sandbox copy holds its source's membership id.
  const workspace = openMembership(me, useShellSession())?.tenant.display_name;
  const formId = useId();
  const toast = useToast();
  const roles = useActiveRoles();
  const rules = useSodRules();
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  // §9.10 (rev 1.60): the inviter gives no scope beyond their own `user.manage` (04 T-PLT-10).
  const scope = useAccess().scope(USER_MANAGE_PERMISSION);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [drafts, setDrafts] = useState<readonly RoleGrantDraft[]>(() => [newGrantDraft(scope)]);
  const [attempted, setAttempted] = useState(false);
  const [hint, setHint] = useState(false);
  const invite = useCommand<UserItem>({
    method: "POST",
    path: USERS_PATH,
    invalidates: [EVERY_USER],
  });
  const conflicts = useMemo(
    () =>
      sodConflicts(
        permissionsOf(
          drafts.map((draft) => draft.roleId),
          roles.data ?? [],
        ),
        rules.data ?? [],
      ),
    [drafts, roles.data, rules.data],
  );
  const emailError =
    attempted && email.trim() === "" ? t("access.users.invite.emailRequired") : null;
  const nameError =
    attempted && displayName.trim() === "" ? t("access.users.invite.displayNameRequired") : null;

  const submit = async () => {
    setAttempted(true);
    if (email.trim() === "" || displayName.trim() === "" || !grantsValid(drafts)) {
      return;
    }
    const body: UserInvite = {
      email: email.trim(),
      display_name: displayName.trim(),
      roles: drafts.map(toGrant),
    };
    const outcome = await invite.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message:
          invitationOutcome(outcome.data) === "bootstrap"
            ? t("access.users.invite.sent.bootstrap")
            : t("access.users.invite.sent.pending", { email: outcome.data.email }),
      });
      onClose();
    }
  };

  const dirty = email !== "" || displayName !== "" || drafts.some((draft) => draft.roleId !== null);
  const placed = useMemo(
    () => placeProblemByEnd(invite.problem, inviteFields(drafts)),
    [invite.problem, drafts],
  );
  const apiEmail = placed.fields.email ?? null;
  const apiName = placed.fields.name ?? null;

  return (
    <Drawer
      open
      title={t("access.users.invite.title")}
      subtitle={workspace}
      initialFocus="field"
      dirty={dirty}
      submitting={invite.pending}
      banner={
        <>
          <RefusalBanner problem={invite.problem} placed={placed} />
          <SodConflictBanner
            rules={conflicts}
            onRequestException={() => {
              setHint(true);
            }}
          />
          {hint && conflicts.length > 0 ? (
            <p className="text-body-sm text-fg-2">
              {t("access.users.invite.exceptionAfterInvite")}
            </p>
          ) : null}
        </>
      }
      primaryAction={{ label: t("access.users.invite.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-14-drawer-invite"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Field
          name="invite-email"
          label={t("access.users.invite.email")}
          required
          error={apiEmail ?? emailError}
        >
          {(control) => (
            <input
              {...control}
              type="email"
              autoComplete="off"
              spellCheck={false}
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              className={controlClass(control["aria-invalid"] === true)}
            />
          )}
        </Field>
        <Field
          name="invite-display-name"
          label={t("access.users.invite.displayName")}
          required
          error={apiName ?? nameError}
        >
          {(control) => (
            <input
              {...control}
              type="text"
              autoComplete="off"
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
              }}
              className={controlClass(control["aria-invalid"] === true)}
            />
          )}
        </Field>
        <fieldset className="flex flex-col gap-2">
          <legend className="text-body-sm font-medium text-fg-1">
            {t("access.users.invite.roles")}
          </legend>
          <RoleGrantRows
            drafts={drafts}
            onChange={setDrafts}
            roles={roles.data ?? []}
            entities={entities.data ?? []}
            scope={scope}
            findings={(index) => ({
              entities: placed.fields[`entities:${String(index)}`] ?? null,
              all: placed.fields[`all:${String(index)}`] ?? null,
            })}
            attempted={attempted}
            repeatable
          />
        </fieldset>
      </form>
    </Drawer>
  );
}
