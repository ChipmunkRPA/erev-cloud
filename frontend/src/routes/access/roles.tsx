// SF-14:roles Roles (SCREENS_B §9.11; SCREENS §0.4 RT-88, §0.3 SCR-IA-03, §0.7 SCR-PERM-01; DESIGN_SYSTEM
// DS-CMP-09, DS-CMP-10, DS-CMP-19, DS-CMP-21, DS-CMP-29; 04 API-R-06 `GET /roles`, `GET /roles/{id}`,
// `GET /permissions`, `POST /roles`, `POST /roles/{id}/propose-change`; T-PLT-09, T-PLT-11; REQ-PLT-008,
// REQ-PLT-009; BS1-D-14; BUILD_SPEC WEB-20). The Settings frame with the Access route tabs, the DataGrid
// "Roles" (name, code, system, permission count, members, active) and, beside it, the docked drawer of
// the selected role (`drawer=role&role=<id>`) listing its permissions by area with the "Approval",
// "Access admin" and "MFA" chips; a system role's "Propose change" is unavailable with "System roles
// cannot change.", a custom role's opens the change drawer. "New role" (`role.manage`) takes Name, Code
// (lowercase letters and underscores), Description and permission checkbox groups; an approval
// permission notes the forced MFA and a checked pair that meets a published SoD rule warns and needs
// "I have reviewed this warning"; "Submit for approval" sends `POST /roles`. "Download role matrix" is
// not rendered (BS1-D-14).
import { type ReactNode, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { OutlineChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { type Access, accessOf, useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import { placeProblem } from "../../lib/api/refusals";
import {
  EVERY_ROLE,
  fetchRolesPage,
  groupPermissions,
  type Permission,
  type Role,
  type RoleChangeIn,
  roleCodeValid,
  type RoleCreateIn,
  roleProposeChangePath,
  ROLES_PATH,
  ROLES_ROUTE,
  rolesListKey,
  type SodRule,
  sodConflicts,
  usePermissions,
  useRole,
  useSodRules,
} from "../../lib/api/queries/roles";
import { ROLE_MANAGE_PERMISSION } from "../../lib/api/queries/users";
import { formatNumber } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "../settings/index";

/** The T-PLT-11 area label; an area without a catalogue label shows its code. */
export function areaLabel(area: string): string {
  const key = `access.roles.area.${area}`;
  return hasMessage(key) ? t(key) : area;
}

/** SCREENS_B §9.11 warning: "This role combines <A> with <B> (SoD <n>). Members will need an exception." */
export function rolePairWarning(rule: SodRule): string {
  return t("access.roles.new.sodWarning", {
    functionA: rule.function_a_permissions.join(", "),
    functionB: rule.function_b_permissions.join(", "),
    rule: rule.code.replace("-", " "),
  });
}

function yesNo(value: boolean): string {
  return t(value ? "access.roles.yes" : "access.roles.no");
}

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

/** SCREENS_B §9.11: the role drawer's route, `drawer=role&role=<id>` on the roles page. */
export function roleDrawerRoute(roleId: string): string {
  return `${ROLES_ROUTE}?drawer=role&role=${roleId}`;
}

/** SCREENS_B §9.11 grid columns; the name link opens the drawer. */
export function roleColumns(): readonly GridColumn<Role>[] {
  return [
    {
      id: "name",
      header: t("access.roles.column.role"),
      kind: "identifier",
      value: (role) => role.name,
      href: (role) => roleDrawerRoute(role.id),
      sortKey: "name",
      width: 224,
    },
    {
      id: "code",
      header: t("access.roles.column.code"),
      kind: "text",
      value: (role) => role.code,
      render: (role) => mono(role.code),
      sortKey: "code",
      width: 200,
    },
    {
      id: "is_system",
      header: t("access.roles.column.system"),
      kind: "boolean",
      value: (role) => String(role.is_system),
      width: 96,
    },
    {
      id: "permissions",
      header: t("access.roles.column.permissions"),
      kind: "number",
      numberKind: "count",
      value: (role) => String(role.permissions.length),
      width: 120,
    },
    {
      id: "member_count",
      header: t("access.roles.column.members"),
      kind: "number",
      numberKind: "count",
      value: (role) => String(role.member_count),
      width: 104,
    },
    {
      id: "is_active",
      header: t("access.roles.column.active"),
      kind: "boolean",
      value: (role) => String(role.is_active),
      width: 88,
    },
  ];
}

export function RolesScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.roles.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(ROLE_MANAGE_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.roleManage"),
        })}
      />
    );
  } else {
    return <RolesPage me={me.data} />;
  }
  return (
    <div
      data-testid="SF-14-roles-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

function RolesPage({ me }: { readonly me: Me }) {
  const canDefine = definesRoles(accessOf(me));
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const selectedId = params.get("drawer") === "role" ? params.get("role") : null;
  const title = t("access.roles.title");
  const closeDrawer = () => {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        copy.delete("drawer");
        copy.delete("role");
        return copy;
      },
      { replace: true },
    );
  };
  const columns = useMemo(() => roleColumns(), []);
  const source: GridSource<Role> = { queryKey: rolesListKey(), fetchPage: fetchRolesPage };
  const countLabel = (value: number) =>
    t("access.roles.count", { count: value, formatted: formatNumber(value, { kind: "count" }) });

  return (
    <div
      data-testid="SF-14-roles-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <DataGrid<Role>
            name="roles"
            title={t("access.roles.grid")}
            errorTitle={t("access.roles.loadError")}
            countLabel={(value, formatted) => t("access.roles.count", { count: value, formatted })}
            columns={columns}
            source={source}
            rowKey={(role) => role.id}
            rowLabel={(role) => role.name}
            testIdPrefix="SF-14"
            rowTestKey={(role) => role.code}
            onTotalChange={(next) => setTotal(next?.count)}
            toolbarActions={
              canDefine ? (
                <Button
                  variant="primary"
                  onClick={() => {
                    setCreating(true);
                  }}
                >
                  {t("access.roles.new.title")}
                </Button>
              ) : undefined
            }
          />
        </div>
        {selectedId === null ? null : <RoleDrawer roleId={selectedId} onClose={closeDrawer} />}
      </div>
      {creating ? (
        <NewRoleDrawer
          onClose={() => {
            setCreating(false);
          }}
        />
      ) : null}
    </div>
  );
}

/** SCREENS_B §9.11 drawer permission rows: code, description and the T-PLT-11 flag chips. */
export function PermissionFlags({ permission }: { readonly permission: Permission }) {
  return (
    <span className="flex flex-wrap gap-1">
      {permission.is_approval ? <OutlineChip label={t("access.roles.flag.approval")} /> : null}
      {permission.is_access_admin ? (
        <OutlineChip label={t("access.roles.flag.accessAdmin")} />
      ) : null}
      {permission.requires_mfa ? <OutlineChip label={t("access.roles.flag.mfa")} /> : null}
    </span>
  );
}

/**
 * §9.11 (rev 1.60; 04 T-PLT-10): a role's definition is a tenant-wide act. "New role" and "Propose
 * change" need `role.manage` for all entities; a holder for named entities reads the roles.
 */
function definesRoles(access: Access): boolean {
  return access.holdsForAll(ROLE_MANAGE_PERMISSION);
}

interface RoleDrawerProps {
  readonly roleId: string;
  readonly onClose: () => void;
}

/** The docked informational drawer of a role (`drawer=role`). */
function RoleDrawer({ roleId, onClose }: RoleDrawerProps) {
  const canDefine = definesRoles(useAccess());
  const role = useRole(roleId);
  const permissions = usePermissions();
  const [changing, setChanging] = useState(false);
  const title = role.data?.name ?? t("access.roles.drawer.loading");
  const catalogue = permissions.data ?? [];
  const held = new Set(role.data?.permissions ?? []);
  const groups = groupPermissions(catalogue.filter((permission) => held.has(permission.code)));
  return (
    <>
      <Drawer
        open
        variant="docked"
        title={title}
        subtitle={
          role.data === undefined
            ? undefined
            : t(role.data.is_system ? "access.roles.drawer.system" : "access.roles.drawer.custom", {
                code: role.data.code,
              })
        }
        initialFocus="title"
        onClose={onClose}
      >
        <div data-testid="SF-14-drawer-role" className="flex flex-col gap-4">
          {role.isError ? <Banner tone="negative" title={role.error.message} /> : null}
          {role.data === undefined && !role.isError ? (
            <Skeleton region={title} shape="rows" count={4} />
          ) : null}
          {role.data === undefined ? null : (
            <>
              {role.data.description === null ? null : (
                <p className="text-body-sm text-fg-2">{role.data.description}</p>
              )}
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body-sm">
                <dt className="text-fg-3">{t("access.roles.column.members")}</dt>
                <dd className="num text-fg-1">
                  {formatNumber(role.data.member_count, { kind: "count" })}
                </dd>
                <dt className="text-fg-3">{t("access.roles.column.active")}</dt>
                <dd className="text-fg-1">{yesNo(role.data.is_active)}</dd>
              </dl>
              {canDefine ? (
                <div>
                  <Button
                    variant="secondary"
                    disabledReason={
                      role.data.is_system ? t("access.roles.drawer.systemLocked") : undefined
                    }
                    onClick={() => {
                      setChanging(true);
                    }}
                  >
                    {t("access.roles.drawer.proposeChange")}
                  </Button>
                </div>
              ) : null}
              {groups.map(([area, items]) => (
                <section key={area} aria-label={areaLabel(area)} className="flex flex-col gap-1">
                  <h3 className="text-body-sm font-medium text-fg-1">{areaLabel(area)}</h3>
                  <table className="w-full border-collapse text-body-sm">
                    <tbody>
                      {items.map((permission) => (
                        <tr key={permission.code} className="border-b border-hairline align-top">
                          <th scope="row" className="py-1.5 pe-3 text-start font-normal">
                            {mono(permission.code)}
                          </th>
                          <td className="py-1.5 pe-3 text-fg-2">{permission.description}</td>
                          <td className="py-1.5">
                            <PermissionFlags permission={permission} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              ))}
            </>
          )}
        </div>
      </Drawer>
      {changing && role.data !== undefined ? (
        <ProposeChangeDrawer
          role={role.data}
          onClose={() => {
            setChanging(false);
          }}
        />
      ) : null}
    </>
  );
}

interface PermissionGroupsProps {
  readonly permissions: readonly Permission[];
  readonly checked: ReadonlySet<string>;
  readonly onToggle: (code: string, on: boolean) => void;
}

/** SCREENS_B §9.11 checkbox groups by area; each `fieldset` carries the area label as legend. */
export function PermissionGroups({ permissions, checked, onToggle }: PermissionGroupsProps) {
  const base = useId();
  return (
    <div className="flex flex-col gap-4">
      {groupPermissions(permissions).map(([area, items]) => (
        <fieldset key={area} className="flex flex-col gap-1.5">
          <legend className="text-body-sm font-medium text-fg-1">{areaLabel(area)}</legend>
          {items.map((permission) => {
            const id = `${base}-${permission.code}`;
            return (
              <div key={permission.code} className="flex items-start gap-2 text-body-sm text-fg-1">
                <input
                  id={id}
                  type="checkbox"
                  className="mt-0.5 size-4"
                  checked={checked.has(permission.code)}
                  onChange={(event) => {
                    onToggle(permission.code, event.target.checked);
                  }}
                />
                <div className="flex flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-2">
                    <label htmlFor={id} className="font-mono text-mono">
                      {permission.code}
                    </label>
                    <PermissionFlags permission={permission} />
                  </span>
                  <span className="text-fg-2">{permission.description}</span>
                </div>
              </div>
            );
          })}
        </fieldset>
      ))}
    </div>
  );
}

/** The notes and warnings of a permission selection: forced MFA and the SoD pairs it combines. */
function SelectionNotes({
  checked,
  permissions,
  rules,
  reviewed,
  onReviewed,
  attempted,
}: {
  readonly checked: ReadonlySet<string>;
  readonly permissions: readonly Permission[];
  readonly rules: readonly SodRule[];
  readonly reviewed: boolean;
  readonly onReviewed: (value: boolean) => void;
  readonly attempted: boolean;
}) {
  const checkboxId = useId();
  const approval = permissions.some(
    (permission) => checked.has(permission.code) && permission.is_approval,
  );
  const conflicts = sodConflicts(checked, rules);
  return (
    <>
      {approval ? (
        <p data-testid="SF-14-note-approval-mfa" className="text-body-sm text-fg-2">
          {t("access.roles.new.approvalNote")}
        </p>
      ) : null}
      {conflicts.length === 0 ? null : (
        <div data-testid="SF-14-banner-role-sod" className="flex flex-col gap-2">
          {conflicts.map((rule) => (
            <Banner key={rule.code} tone="warning" title={rolePairWarning(rule)} />
          ))}
          <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              className="size-4"
              checked={reviewed}
              onChange={(event) => {
                onReviewed(event.target.checked);
              }}
            />
            {t("access.roles.new.reviewed")}
          </label>
          {attempted && !reviewed ? (
            <p className="text-body-sm text-negative-fg">{t("access.roles.new.reviewRequired")}</p>
          ) : null}
        </div>
      )}
    </>
  );
}

// docs/dev-guide.md DG-FE-06: the fields of "New role" that show a message of the API and the members
// each sends. The description and the permission groups show none: an error there is the banner's.
const ROLE_MEMBERS = { name: ["name"], code: ["code"] } as const;

/** SCREENS_B §9.11 "New role" modal drawer; the role waits for approval (`ROLE_CHANGE`). */
export function NewRoleDrawer({ onClose }: { readonly onClose: () => void }) {
  const formId = useId();
  const toast = useToast();
  const permissions = usePermissions();
  const rules = useSodRules();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [checked, setChecked] = useState<ReadonlySet<string>>(() => new Set());
  const [reviewed, setReviewed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<Role>({ method: "POST", path: ROLES_PATH, invalidates: [EVERY_ROLE] });
  const placed = useMemo(() => placeProblem(create.problem, ROLE_MEMBERS), [create.problem]);
  const conflicts = sodConflicts(checked, rules.data ?? []);
  const nameError = attempted && name.trim() === "" ? t("access.roles.new.nameRequired") : null;
  const codeError = attempted && !roleCodeValid(code) ? t("access.roles.new.codeRule") : null;
  const permissionsError =
    attempted && checked.size === 0 ? t("access.roles.new.permissionsRequired") : null;

  const submit = async () => {
    setAttempted(true);
    if (
      name.trim() === "" ||
      !roleCodeValid(code) ||
      checked.size === 0 ||
      (conflicts.length > 0 && !reviewed)
    ) {
      return;
    }
    const body: RoleCreateIn = {
      code,
      name: name.trim(),
      description: description.trim() === "" ? null : description.trim(),
      permissions: [...checked],
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message:
          outcome.data.pending_approval_request_id === null
            ? t("access.roles.new.created", { name: outcome.data.name })
            : t("access.roles.new.submitted", { name: outcome.data.name }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("access.roles.new.title")}
      initialFocus="field"
      dirty={name !== "" || code !== "" || description !== "" || checked.size > 0}
      submitting={create.pending}
      banner={<RefusalBanner problem={create.problem} placed={placed} />}
      primaryAction={{ label: t("access.roles.new.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-14-drawer-new-role"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <Field
          name="role-name"
          label={t("access.roles.new.name")}
          required
          error={placed.fields.name ?? nameError}
        >
          {(control) => (
            <input
              {...control}
              type="text"
              autoComplete="off"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              className={controlClass(control["aria-invalid"] === true)}
            />
          )}
        </Field>
        <Field
          name="role-code"
          label={t("access.roles.new.code")}
          required
          help={t("access.roles.new.codeRule")}
          error={placed.fields.code ?? codeError}
        >
          {(control) => (
            <input
              {...control}
              type="text"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
              }}
              className={`${controlClass(control["aria-invalid"] === true)} font-mono`}
            />
          )}
        </Field>
        <Field name="role-description" label={t("access.roles.new.description")} optional>
          {(control) => (
            <textarea
              {...control}
              rows={2}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className={controlClass(false, true)}
            />
          )}
        </Field>
        <div className="flex flex-col gap-2">
          <p className="text-body-sm font-medium text-fg-1">{t("access.roles.new.permissions")}</p>
          {permissionsError === null ? null : (
            <p className="text-body-sm text-negative-fg">{permissionsError}</p>
          )}
          {permissions.data === undefined ? (
            <Skeleton region={t("access.roles.new.permissions")} shape="rows" count={4} />
          ) : (
            <PermissionGroups
              permissions={permissions.data}
              checked={checked}
              onToggle={(permissionCode, on) => {
                setChecked((current) => {
                  const next = new Set(current);
                  if (on) {
                    next.add(permissionCode);
                  } else {
                    next.delete(permissionCode);
                  }
                  return next;
                });
              }}
            />
          )}
          <SelectionNotes
            checked={checked}
            permissions={permissions.data ?? []}
            rules={rules.data ?? []}
            reviewed={reviewed}
            onReviewed={setReviewed}
            attempted={attempted}
          />
        </div>
      </form>
    </Drawer>
  );
}

/** SCREENS_B §9.11 change of a custom role's permissions, under approval (`POST /roles/{id}/propose-change`). */
function ProposeChangeDrawer({
  role,
  onClose,
}: {
  readonly role: Role;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const permissions = usePermissions();
  const rules = useSodRules();
  const [checked, setChecked] = useState<ReadonlySet<string>>(() => new Set(role.permissions));
  const [comment, setComment] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const propose = useCommand<Role>({
    method: "POST",
    path: roleProposeChangePath(role.id),
    invalidates: [EVERY_ROLE],
  });
  const conflicts = sodConflicts(checked, rules.data ?? []);
  const unchanged =
    checked.size === role.permissions.length && role.permissions.every((code) => checked.has(code));

  const submit = async () => {
    setAttempted(true);
    if (checked.size === 0 || unchanged || (conflicts.length > 0 && !reviewed)) {
      return;
    }
    const body: RoleChangeIn = {
      permissions: [...checked],
      comment: comment.trim() === "" ? null : comment.trim(),
    };
    const outcome = await propose.submit(body);
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("access.roles.change.submitted", { name: role.name }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("access.roles.change.title")}
      subtitle={role.name}
      initialFocus="field"
      dirty={!unchanged || comment !== ""}
      submitting={propose.pending}
      banner={
        <>
          <RefusalBanner problem={propose.problem} />
          {attempted && unchanged ? (
            <Banner tone="info" announce="live" title={t("access.roles.change.unchanged")} />
          ) : null}
        </>
      }
      primaryAction={{ label: t("access.roles.change.submit"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-14-drawer-role-change"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {permissions.data === undefined ? (
          <Skeleton region={t("access.roles.new.permissions")} shape="rows" count={4} />
        ) : (
          <PermissionGroups
            permissions={permissions.data}
            checked={checked}
            onToggle={(permissionCode, on) => {
              setChecked((current) => {
                const next = new Set(current);
                if (on) {
                  next.add(permissionCode);
                } else {
                  next.delete(permissionCode);
                }
                return next;
              });
            }}
          />
        )}
        <SelectionNotes
          checked={checked}
          permissions={permissions.data ?? []}
          rules={rules.data ?? []}
          reviewed={reviewed}
          onReviewed={setReviewed}
          attempted={attempted}
        />
        <Field name="role-change-comment" label={t("access.roles.change.comment")} optional>
          {(control) => (
            <textarea
              {...control}
              rows={2}
              value={comment}
              onChange={(event) => {
                setComment(event.target.value);
              }}
              className={controlClass(false, true)}
            />
          )}
        </Field>
      </form>
    </Drawer>
  );
}
