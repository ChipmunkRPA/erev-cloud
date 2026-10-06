// SF-14:user User (SCREENS_B §9.10; SCREENS §0.4 RT-108, §0.3 SB-R-05, §0.4 E-78 and SMAP-14 chips,
// SCR-PERM-05; DESIGN_SYSTEM DS-CMP-06, DS-CMP-09, DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-CMP-29; 04 API-R-05
// `GET /users/{id}`, `/suspend`, `/reactivate`, `/remove`, `/reset-mfa`, `/resend-invitation`; API-R-06
// `POST /role-assignments`, `POST /role-assignments/{id}/revoke`; API-R-07 `POST /sod-exceptions`; PRD
// ERR-22; BS1-D-26; BUILD_SPEC WEB-19). The record header (name, email, E-78 chip) with "Reset MFA"
// (step-up), "Suspend" or "Reactivate", "Remove", "Resend invitation" for an invited member and the primary
// "Add role" (`role.manage`); a warning banner on a suspended membership; the static table "Roles" with
// the SMAP-14 chips, "Setup grant" for AUTO-BOOTSTRAP grants, the approval and exception links and
// "Revoke role"; the security line. "Add role" runs the live SoD check and, on a conflict, "Request an
// exception" opens "Request SoD exception" (compensating control, validity of at most 366 days, comment)
// whose answer rides on the assignment. Every reason follows SB-R-05 (at least 10 characters).
// `GET /users/{id}` carries no suspension or lockout timestamps: the suspended banner shows the
// membership's last change, and the security line shows the MFA state only (lane record F-ADM).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";
import { Link, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { type Access, type EntityOf, useAccess } from "../../lib/access";
import { useMe } from "../../lib/api/queries/me";
import { placeProblem } from "../../lib/api/refusals";
import {
  idPrefix,
  permissionsOf,
  type Role,
  ROLE_ASSIGNMENTS_PATH,
  type RoleAssignment,
  type RoleAssignmentIn,
  roleAssignmentRevokePath,
  SOD_EXCEPTIONS_PATH,
  SOD_ROUTE,
  type SodException,
  type SodExceptionIn,
  type SodRule,
  sodConflicts,
  useActiveRoles,
  useSodRules,
  validityWithinLimit,
} from "../../lib/api/queries/roles";
import { type Entity, entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import {
  currentRoles,
  EVERY_USER,
  type MembershipAction,
  ROLE_MANAGE_PERMISSION,
  scopeCodes,
  USER_MANAGE_PERMISSION,
  userActionPath,
  type UserItem,
  userKey,
  type UserRole,
  USERS_ROUTE,
  useUser,
} from "../../lib/api/queries/users";
import { dayEndInstant, dayStartInstant, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SETTINGS_PATH, useBuiltPaths } from "../settings/index";
import { StepUpModal } from "../settings/profile";
import {
  grantsValid,
  newGrantDraft,
  type RoleGrantDraft,
  RoleGrantRows,
  SodConflictBanner,
  toGrant,
} from "./role-fields";

/** SCREENS RT-57 SF-12:request. */
export const APPROVAL_REQUEST_ROUTE = "/approvals/requests/:requestId";

function approvalRoute(requestId: string): string {
  return `/approvals/requests/${requestId}`;
}

/** SCREENS §0.4 SMAP-14: the assignment status chip word. */
export function assignmentChip(status: UserRole["status"]): string {
  return chipFor("SMAP-14", status.toLowerCase())?.status ?? status;
}

export function UserPage() {
  const { membershipId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const user = useUser(membershipId);
  const title = t("access.user.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(USER_MANAGE_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("access.users.title") })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.userManage"),
        })}
      />
    );
  } else if (user.isError) {
    body = (
      <Banner tone="negative" title={t("access.user.loadError")}>
        {user.error.message}
      </Banner>
    );
  } else if (user.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else {
    return <UserRecord access={access} user={user.data} />;
  }
  return (
    <div
      data-testid="SF-14-user-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      {body}
    </div>
  );
}

type Dialog =
  | { readonly kind: "none" }
  | { readonly kind: "action"; readonly action: MembershipAction }
  | { readonly kind: "revoke"; readonly role: UserRole }
  | { readonly kind: "add-role" };

/**
 * The entities a member's roles name (04 T-PLT-10): `"*"` when one of them is for all entities. A
 * requested role is no assignment yet, and a revoked one grants nothing.
 */
export function grantedEntities(roles: readonly UserRole[]): readonly EntityOf[] | "*" {
  const held = roles.filter((role) => role.assignment_id !== null && role.status !== "REVOKED");
  return held.some((role) => role.is_all_entities) ? "*" : held.flatMap((role) => role.entities);
}

/**
 * SCREENS_B §9.10 (rev 1.105; 04 T-PLT-02 rev 1.316) the security line: the MFA state of a member; for an
 * invited or a removed member API-S-User answers `sign_in_withheld` and null — not shown, which is not
 * "MFA not enrolled".
 */
function securityLine(user: Pick<UserItem, "mfa_enrolled" | "sign_in_withheld">): string {
  if (user.sign_in_withheld) {
    return t("access.user.signInNotShown");
  }
  return t(user.mfa_enrolled === true ? "access.user.mfaEnrolled" : "access.user.mfaNotEnrolled");
}

function UserRecord({ access, user }: { readonly access: Access; readonly user: UserItem }) {
  const built = useBuiltPaths();
  // §9.10 (rev 1.60; 04 T-PLT-10): "Add role" for `role.manage` held for any entity — its scope
  // field offers what that covers; a command on the member for `user.manage` held for every entity
  // the member's roles name; "Revoke role" for `role.manage` over the role's own entities.
  const canManageRoles = access.holdsAnywhere(ROLE_MANAGE_PERMISSION);
  const canManageMember = access.holdsForEvery(USER_MANAGE_PERMISSION, grantedEntities(user.roles));
  const canRevoke = (role: UserRole) =>
    access.holdsForEvery(ROLE_MANAGE_PERMISSION, role.is_all_entities ? "*" : role.entities);
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const roles = useActiveRoles(canManageRoles);
  const rules = useSodRules(canManageRoles);
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: canManageRoles,
  });
  const close = () => {
    setDialog({ kind: "none" });
  };
  const chip = chipFor("E-78", user.status);
  const actions: ReactNode[] = [];
  if (canManageMember && user.status === "INVITED") {
    actions.push(
      <Button
        key="resend"
        variant="secondary"
        onClick={() => setDialog({ kind: "action", action: "resend-invitation" })}
      >
        {t("access.user.resendInvitation")}
      </Button>,
    );
  }
  if (canManageMember && user.status !== "REMOVED") {
    actions.push(
      <Button
        key="reset-mfa"
        variant="secondary"
        onClick={() => setDialog({ kind: "action", action: "reset-mfa" })}
      >
        {t("access.user.resetMfa")}
      </Button>,
    );
  }
  if (canManageMember && user.status === "ACTIVE") {
    actions.push(
      <Button
        key="suspend"
        variant="secondary"
        onClick={() => setDialog({ kind: "action", action: "suspend" })}
      >
        {t("access.user.suspend")}
      </Button>,
    );
  }
  if (canManageMember && user.status === "SUSPENDED") {
    actions.push(
      <Button
        key="reactivate"
        variant="secondary"
        onClick={() => setDialog({ kind: "action", action: "reactivate" })}
      >
        {t("access.user.reactivate")}
      </Button>,
    );
  }
  if (canManageMember && user.status !== "REMOVED") {
    actions.push(
      <Button
        key="remove"
        variant="ghost"
        onClick={() => setDialog({ kind: "action", action: "remove" })}
      >
        {t("access.user.remove")}
      </Button>,
    );
  }
  const addRole =
    canManageRoles && user.status !== "REMOVED" ? (
      <Button key="add-role" variant="primary" onClick={() => setDialog({ kind: "add-role" })}>
        {t("access.user.addRole")}
      </Button>
    ) : null;
  if (addRole !== null) {
    actions.push(addRole);
  }

  return (
    <div
      data-testid="SF-14-user-page"
      className="flex w-full flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <RecordHeader
        title={user.display_name}
        breadcrumb={[
          { label: t("settings.index.title"), to: SETTINGS_PATH },
          { label: t("access.users.title"), to: USERS_ROUTE },
        ]}
        chips={chip === null ? null : <StatusChip status={chip.status} />}
        meta={[{ label: t("access.user.email"), value: user.email }]}
        actions={actions}
        primaryAction={addRole ?? undefined}
        banner={
          user.status === "SUSPENDED" ? (
            <div data-testid="SF-14-banner-suspended">
              <Banner
                tone="warning"
                announce="static"
                title={t("access.user.suspended", { timestamp: formatTimestamp(user.updated_at) })}
              />
            </div>
          ) : undefined
        }
      />
      <RolesTable
        user={user}
        canManageRoles={canManageRoles}
        canRevoke={canRevoke}
        approvalsBuilt={built.has(APPROVAL_REQUEST_ROUTE)}
        sodBuilt={built.has(SOD_ROUTE)}
        onRevoke={(role) => setDialog({ kind: "revoke", role })}
      />
      <section aria-label={t("access.user.security")} className="flex flex-col gap-1">
        <h2 className="text-title-sm text-fg-1">{t("access.user.security")}</h2>
        <p className="text-body-sm text-fg-2">{securityLine(user)}</p>
      </section>

      {dialog.kind === "action" ? (
        <MembershipActionDialog user={user} action={dialog.action} onClose={close} />
      ) : null}
      {dialog.kind === "revoke" ? (
        <RevokeRoleDialog user={user} role={dialog.role} onClose={close} />
      ) : null}
      {dialog.kind === "add-role" ? (
        <AddRoleDrawer
          user={user}
          roles={roles.data ?? []}
          rules={rules.data ?? []}
          entities={entities.data ?? []}
          onClose={close}
        />
      ) : null}
    </div>
  );
}

interface RolesTableProps {
  readonly user: UserItem;
  readonly canManageRoles: boolean;
  /** The viewer's `role.manage` covers the entities of this role. */
  readonly canRevoke: (role: UserRole) => boolean;
  readonly approvalsBuilt: boolean;
  readonly sodBuilt: boolean;
  readonly onRevoke: (role: UserRole) => void;
}

const CELL = "px-3 py-2 text-body-sm align-top";
const HEAD = "px-3 py-2 text-start text-caption font-medium text-fg-3";

/** SCREENS_B §9.10 "Roles" static table. */
function RolesTable({
  user,
  canManageRoles,
  canRevoke,
  approvalsBuilt,
  sodBuilt,
  onRevoke,
}: RolesTableProps) {
  const headingId = useId();
  const roles = user.roles;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("access.user.roles.title")}
      </h2>
      <table
        aria-labelledby={headingId}
        data-testid="SF-14-grid-user-roles"
        className="w-full border-collapse"
      >
        <thead>
          <tr className="border-b border-hairline">
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.role")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.scope")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.status")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.granted")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.grantedBy")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.approval")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.exception")}
            </th>
            <th scope="col" className={HEAD}>
              {t("access.user.roles.column.revoked")}
            </th>
            {canManageRoles ? (
              <th scope="col" className={HEAD}>
                {t("access.user.roles.column.actions")}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {roles.length === 0 ? (
            <tr>
              <td className={`${CELL} text-fg-3`} colSpan={canManageRoles ? 9 : 8}>
                {t("access.user.roles.empty")}
              </td>
            </tr>
          ) : null}
          {roles.map((role) => (
            <tr
              key={role.assignment_id ?? `${role.role.id}-${role.status}`}
              className="border-b border-hairline"
            >
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {role.role.name}
              </th>
              <td className={CELL}>{scopeCodes(role) ?? t("access.users.scope.all")}</td>
              <td className={CELL}>
                <StatusChip status={assignmentChip(role.status)} />
              </td>
              <td className={`${CELL} num`}>
                {role.granted_at === null ? NO_VALUE : formatTimestamp(role.granted_at)}
              </td>
              <td className={CELL}>
                {role.setup_grant ? (
                  <OutlineChip label={t("access.user.roles.setupGrant")} />
                ) : (
                  (role.granted_by?.display_name ?? NO_VALUE)
                )}
              </td>
              <td className={CELL}>
                {role.approval_request_id === null ? (
                  NO_VALUE
                ) : approvalsBuilt ? (
                  <Link
                    to={approvalRoute(role.approval_request_id)}
                    className="text-accent-fg hover:underline"
                  >
                    {t("access.user.roles.approvalLink")}
                  </Link>
                ) : (
                  t("access.user.roles.approvalLink")
                )}
              </td>
              <td className={`${CELL} font-mono`}>
                {role.sod_exception_id === null ? (
                  NO_VALUE
                ) : sodBuilt ? (
                  <Link
                    to={`${SOD_ROUTE}?pane=exceptions`}
                    className="text-accent-fg hover:underline"
                  >
                    {idPrefix(role.sod_exception_id)}
                  </Link>
                ) : (
                  idPrefix(role.sod_exception_id)
                )}
              </td>
              <td className={`${CELL} num`}>
                {role.revoked_at === null ? NO_VALUE : formatTimestamp(role.revoked_at)}
              </td>
              {canManageRoles ? (
                <td className={CELL}>
                  {role.status === "REVOKED" ||
                  role.assignment_id === null ||
                  !canRevoke(role) ? null : (
                    <Button variant="link" size="sm" onClick={() => onRevoke(role)}>
                      {t("access.user.roles.revoke")}
                    </Button>
                  )}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

interface ActionCopy {
  readonly title: string;
  readonly description: string;
  readonly confirm: string;
  readonly toast: string;
  readonly destructive: boolean;
  readonly reason: boolean;
}

function actionCopy(action: MembershipAction, user: UserItem): ActionCopy {
  const params = { name: user.display_name, email: user.email };
  switch (action) {
    case "suspend":
      return {
        title: t("access.user.suspendDialog.title", params),
        description: t("access.user.suspendDialog.description", params),
        confirm: t("access.user.suspendDialog.confirm"),
        toast: t("access.user.toast.suspended", params),
        destructive: true,
        reason: true,
      };
    case "remove":
      return {
        title: t("access.user.removeDialog.title", params),
        description: t("access.user.removeDialog.description", params),
        confirm: t("access.user.removeDialog.confirm"),
        toast: t("access.user.toast.removed", params),
        destructive: true,
        reason: true,
      };
    case "reset-mfa":
      return {
        title: t("access.user.resetMfaDialog.title", params),
        description: t("access.user.resetMfaDialog.description", params),
        confirm: t("access.user.resetMfaDialog.confirm"),
        toast: t("access.user.toast.mfaReset", params),
        destructive: true,
        reason: true,
      };
    case "reactivate":
      return {
        title: t("access.user.reactivateDialog.title", params),
        description: t("access.user.reactivateDialog.description", params),
        confirm: t("access.user.reactivateDialog.confirm"),
        toast: t("access.user.toast.reactivated", params),
        destructive: false,
        reason: false,
      };
    case "resend-invitation":
      return {
        title: t("access.user.resendDialog.title", params),
        description: t("access.user.resendDialog.description", params),
        confirm: t("access.user.resendDialog.confirm"),
        toast: t("access.user.toast.resent", params),
        destructive: false,
        reason: false,
      };
  }
}

interface MembershipActionDialogProps {
  readonly user: UserItem;
  readonly action: MembershipAction;
  readonly onClose: () => void;
}

/** SB-R-05 confirmations of the membership commands; "Reset MFA" resends after a step-up (SCR-PERM-05). */
export function MembershipActionDialog({ user, action, onClose }: MembershipActionDialogProps) {
  const formId = useId();
  const toast = useToast();
  const copy = actionCopy(action, user);
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const command = useCommand<UserItem>({
    method: "POST",
    path: userActionPath(user.id, action),
    invalidates: [userKey(user.id), EVERY_USER],
  });

  const send = async () => {
    const outcome = await command.submit(copy.reason ? { reason: reason.trim() } : {});
    if (outcome.kind === "failed" && outcome.problem.slug === "mfa-step-up-required") {
      setStepUp(true);
      return;
    }
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: copy.toast });
      onClose();
    }
  };
  const submit = () => {
    setAttempted(true);
    if (copy.reason && reasonError(reason) !== null) {
      return;
    }
    void send();
  };

  if (stepUp) {
    return (
      <StepUpModal
        onCancel={() => {
          setStepUp(false);
        }}
        onVerified={() => {
          setStepUp(false);
          void send();
        }}
      />
    );
  }
  return (
    <Modal
      open
      variant={copy.reason ? "form" : "confirmation"}
      title={copy.title}
      description={copy.description}
      primaryAction={{ label: copy.confirm, destructive: copy.destructive, form: formId }}
      submitting={command.pending}
      onClose={onClose}
      testId={`SF-14-dialog-${action}`}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <RefusalBanner problem={command.problem} />
        {copy.reason ? (
          <ReasonField
            label={t("access.user.reason")}
            value={reason}
            onChange={setReason}
            showError={attempted}
          />
        ) : null}
      </form>
    </Modal>
  );
}

interface RevokeRoleDialogProps {
  readonly user: UserItem;
  readonly role: UserRole;
  readonly onClose: () => void;
}

function RevokeRoleDialog({ user, role, onClose }: RevokeRoleDialogProps) {
  const formId = useId();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const revoke = useCommand<RoleAssignment>({
    method: "POST",
    path: roleAssignmentRevokePath(role.assignment_id ?? ""),
    invalidates: [userKey(user.id), EVERY_USER],
  });
  const params = { role: role.role.name, name: user.display_name };
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await revoke.submit({ reason: reason.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("access.user.toast.revoked", params) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("access.user.revokeDialog.title", params)}
      description={t("access.user.revokeDialog.description", params)}
      primaryAction={{
        label: t("access.user.revokeDialog.confirm"),
        destructive: true,
        form: formId,
      }}
      submitting={revoke.pending}
      onClose={onClose}
      testId="SF-14-dialog-revoke-role"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={revoke.problem} />
        <ReasonField
          label={t("access.user.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </form>
    </Modal>
  );
}

interface AddRoleDrawerProps {
  readonly user: UserItem;
  readonly roles: readonly Role[];
  readonly rules: readonly SodRule[];
  readonly entities: readonly Entity[];
  readonly onClose: () => void;
}

// docs/dev-guide.md DG-FE-06: the two places of the scope row that show a finding of the API (04
// T-PLT-10) and the members each sends. The role select shows none: an error there is the banner's.
const ASSIGNMENT_MEMBERS = { entities: ["entity_codes"], all: ["is_all_entities"] } as const;
// The entities are on screen only while the scope is "Selected entities".
const ASSIGNMENT_MEMBERS_OF_ALL_ENTITIES = { ...ASSIGNMENT_MEMBERS, entities: [] } as const;
// The fields of "Request SoD exception" that show a message of the API; the two dates show none.
const EXCEPTION_MEMBERS = { control: ["compensating_control"], comment: ["comment"] } as const;

/** SCREENS_B §9.10 "Add role": one Role and Scope row, the live SoD check and the exception hand-off. */
export function AddRoleDrawer({ user, roles, rules, entities, onClose }: AddRoleDrawerProps) {
  const formId = useId();
  const toast = useToast();
  // §9.10 (rev 1.60): the grantor gives no scope beyond their own `role.manage` (04 T-PLT-10).
  const scope = useAccess().scope(ROLE_MANAGE_PERMISSION);
  const [drafts, setDrafts] = useState<readonly RoleGrantDraft[]>(() => [newGrantDraft(scope)]);
  const [attempted, setAttempted] = useState(false);
  const [exceptionFor, setExceptionFor] = useState<SodRule | null>(null);
  const [exception, setException] = useState<SodException | null>(null);
  const assign = useCommand<RoleAssignment>({
    method: "POST",
    path: ROLE_ASSIGNMENTS_PATH,
    invalidates: [userKey(user.id), EVERY_USER],
  });
  const draft = drafts[0] ?? newGrantDraft(scope);
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof ASSIGNMENT_MEMBERS>(
        assign.problem,
        draft.allEntities ? ASSIGNMENT_MEMBERS_OF_ALL_ENTITIES : ASSIGNMENT_MEMBERS,
      ),
    [assign.problem, draft.allEntities],
  );
  const conflicts = useMemo(() => {
    const adding = permissionsOf([draft.roleId], roles);
    if (adding.size === 0) {
      return [];
    }
    const held = new Set<string>([
      ...permissionsOf(
        currentRoles(user).map((role) => role.role.id),
        roles,
      ),
      ...adding,
    ]);
    return sodConflicts(held, rules).filter(
      (rule) =>
        rule.function_a_permissions.some((code) => adding.has(code)) ||
        rule.function_b_permissions.some((code) => adding.has(code)),
    );
  }, [draft.roleId, roles, rules, user]);

  const submit = async () => {
    setAttempted(true);
    if (!grantsValid(drafts)) {
      return;
    }
    const grant = toGrant(draft);
    const body: RoleAssignmentIn = {
      membership_id: user.id,
      role_id: grant.role_id,
      is_all_entities: grant.is_all_entities,
      ...(grant.entity_codes === undefined ? {} : { entity_codes: grant.entity_codes }),
      ...(exception === null ? {} : { sod_exception_id: exception.id }),
    };
    const outcome = await assign.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      const roleName = outcome.data.role.name;
      toast.show({
        tone: "positive",
        message:
          outcome.data.status === "REQUESTED"
            ? t("access.user.toast.roleRequested", { role: roleName })
            : t("access.user.toast.roleGranted", { role: roleName }),
      });
      onClose();
    }
  };

  if (exceptionFor !== null) {
    return (
      <ExceptionDrawer
        user={user}
        rule={exceptionFor}
        onClose={() => {
          setExceptionFor(null);
        }}
        onRequested={(requested) => {
          setException(requested);
          setExceptionFor(null);
        }}
      />
    );
  }
  return (
    <Drawer
      open
      title={t("access.user.addRole")}
      subtitle={user.display_name}
      initialFocus="field"
      dirty={draft.roleId !== null}
      submitting={assign.pending}
      banner={
        <>
          <RefusalBanner problem={assign.problem} placed={placed} />
          <SodConflictBanner rules={conflicts} onRequestException={setExceptionFor} />
          {exception === null ? null : (
            <p className="text-body-sm text-fg-2">
              {t("access.user.exception.attached", { id: idPrefix(exception.id) })}
            </p>
          )}
        </>
      }
      primaryAction={{ label: t("access.user.addRoleDrawer.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-14-drawer-add-role"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RoleGrantRows
          drafts={drafts}
          onChange={setDrafts}
          roles={roles}
          entities={entities}
          scope={scope}
          findings={() => placed.fields}
          attempted={attempted}
          repeatable={false}
        />
      </form>
    </Drawer>
  );
}

interface ExceptionDrawerProps {
  readonly user: UserItem;
  readonly rule: SodRule;
  readonly onClose: () => void;
  readonly onRequested: (exception: SodException) => void;
}

/** SCREENS_B §9.10 "Request SoD exception" (SB-R-05 on the compensating control; validity ≤ 366 days). */
export function ExceptionDrawer({ user, rule, onClose, onRequested }: ExceptionDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const [control, setControl] = useState("");
  const [fromText, setFromText] = useState("");
  const [toText, setToText] = useState("");
  const [validFrom, setValidFrom] = useState<string | null>(null);
  const [validTo, setValidTo] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const request = useCommand<SodException>({
    method: "POST",
    path: SOD_EXCEPTIONS_PATH,
    invalidates: [userKey(user.id)],
  });
  const placed = useMemo(() => placeProblem(request.problem, EXCEPTION_MEMBERS), [request.problem]);
  const fromError =
    attempted && validFrom === null ? t("access.user.exception.dateRequired") : null;
  const validityError =
    validFrom !== null && validTo !== null && !validityWithinLimit(validFrom, validTo)
      ? t("access.user.exception.validity")
      : attempted && validTo === null
        ? t("access.user.exception.dateRequired")
        : null;

  const submit = async () => {
    setAttempted(true);
    if (
      reasonError(control) !== null ||
      reasonError(comment) !== null ||
      validFrom === null ||
      validTo === null ||
      !validityWithinLimit(validFrom, validTo)
    ) {
      return;
    }
    const body: SodExceptionIn = {
      membership_id: user.id,
      sod_rule_code: rule.code,
      compensating_control: control.trim(),
      // DS-I18N-08 (R-59): a window of whole days in platform time, its last day included.
      valid_from: dayStartInstant(validFrom),
      valid_to: dayEndInstant(validTo),
      comment: comment.trim(),
    };
    const outcome = await request.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("access.user.exception.requested", { rule: rule.code }),
      });
      onRequested(outcome.data);
    }
  };

  return (
    <Drawer
      open
      title={t("access.user.exception.title")}
      subtitle={user.display_name}
      initialFocus="field"
      dirty={control !== "" || comment !== "" || fromText !== "" || toText !== ""}
      submitting={request.pending}
      banner={<RefusalBanner problem={request.problem} placed={placed} />}
      primaryAction={{ label: t("access.user.exception.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-14-drawer-sod-exception"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Field name="exception-rule" label={t("access.user.exception.rule")}>
          {(controlProps) => (
            <input
              {...controlProps}
              type="text"
              readOnly
              value={`${rule.code} · ${rule.name}`}
              className={controlClass(false)}
            />
          )}
        </Field>
        <ReasonField
          name="compensating_control"
          label={t("access.user.exception.control")}
          value={control}
          onChange={setControl}
          showError={attempted}
          error={placed.fields.control}
        />
        <div className="flex flex-wrap gap-4">
          <Field
            name="valid_from"
            label={t("access.user.exception.validFrom")}
            required
            width="date"
            error={fromError}
          >
            {(controlProps) => (
              <DateInput
                control={controlProps}
                value={fromText}
                onChange={setFromText}
                onValue={setValidFrom}
                invalid={fromError !== null}
              />
            )}
          </Field>
          <Field
            name="valid_to"
            label={t("access.user.exception.validTo")}
            required
            width="date"
            error={validityError}
          >
            {(controlProps) => (
              <DateInput
                control={controlProps}
                value={toText}
                onChange={setToText}
                onValue={setValidTo}
                invalid={validityError !== null}
              />
            )}
          </Field>
        </div>
        <ReasonField
          name="comment"
          label={t("access.user.exception.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
          error={placed.fields.comment}
        />
      </form>
    </Drawer>
  );
}
