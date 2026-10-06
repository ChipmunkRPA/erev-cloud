// SF-12:delegations (SCREENS §15.7, §0.4 RT-58, §0.6 SCR-PERM-01, SCR-PERM-05; DESIGN_SYSTEM DS-CMP-09,
// DS-CMP-10, DS-CMP-11, DS-CMP-20, DS-CMP-23; 04 API-R-09 `GET, POST /approval-delegations`, `POST
// /approval-delegations/{id}/revoke`, T-PLT-21; PRD BR-PLT-06, BR-PLT-07; REQ-PLT-013; BUILD_SPEC WEB-16).
// The Approvals header with its route tabs, the grid of the delegations the member gave and received,
// "New delegation" and "Revoke delegation". The status is read from `revoked_at` and the two instants:
// T-PLT-21 stores none. A delegation is a window of whole days in platform time: "Valid from" is sent
// as 00:00:00Z and "Valid to" as 23:59:59Z of the last day, at most 90 days in all. Creating and
// revoking are access administration: a 403 `mfa-step-up-required` opens the step-up dialog and the
// command is sent again with the same key. Only the delegator revokes. The delegate is chosen from
// `GET /users`, which needs `user.manage`: without it "New delegation" states why it is unavailable.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, useId, useMemo, useState } from "react";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  DEFAULT_WIDTH,
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Combobox } from "../../components/form/Combobox";
import { DateInput } from "../../components/form/DateInput";
import { Field } from "../../components/form/Field";
import { reasonError, ReasonField } from "../../components/form/ReasonField";
import { WarningCircle } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { StatusChip, type StatusWord } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  delegateChoicesKey,
  type Delegation,
  type DelegationCreate,
  type DelegationRevoke,
  DELEGATIONS_PATH,
  delegationsKey,
  type DelegationStatus,
  delegationStatus,
  delegationWithinLimit,
  EVERY_DELEGATION,
  fetchDelegateChoices,
  fetchDelegationsPage,
  revokePath,
} from "../../lib/api/queries/approval-delegations";
import { APPROVAL_PERMISSIONS, holdsApprovalPermission } from "../../lib/api/queries/approvals";
import { type Me, useMe } from "../../lib/api/queries/me";
import { placeProblem } from "../../lib/api/refusals";
import { USER_MANAGE_PERMISSION } from "../../lib/api/queries/users";
import {
  dayEndInstant,
  dayStartInstant,
  formatDate,
  formatList,
  timestampDate,
  utcDateOf,
} from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { StepUpModal } from "../settings/profile";
import { ApprovalsHeader } from "./tabs";

const STEP_UP_REQUIRED_SLUG = "mfa-step-up-required";

/** SCREENS §15.7 Status words; a delegation whose first day is still ahead reads "Not started". */
const STATUS_WORD: Readonly<Record<DelegationStatus, StatusWord>> = {
  ACTIVE: "Active",
  REVOKED: "Revoked",
  EXPIRED: "Expired",
  NOT_STARTED: "Not started",
};

/** The label of an approval permission (T-PLT-11 description); a code the catalogue lacks stays a code. */
export function permissionLabel(code: string): string {
  const key = `approvals.permission.${code}`;
  return hasMessage(key) ? t(key) : code;
}

/** The viewer's approval permissions in catalogue order (SCREENS §15.7 "Permissions"). */
export function ownApprovalPermissions(access: Access): readonly string[] {
  return [...APPROVAL_PERMISSIONS].filter((code) => access.holdsAnywhere(code));
}

/** True for a delegation the member gave that is still to end: the delegator alone revokes (API-R-09). */
export function revocable(
  delegation: Delegation,
  membershipId: string | null,
  nowMs: number,
): boolean {
  const status = delegationStatus(delegation, nowMs);
  return (
    delegation.delegator_membership_id === membershipId &&
    (status === "ACTIVE" || status === "NOT_STARTED")
  );
}

export interface DelegationColumnOptions {
  readonly membershipId: string | null;
  readonly nowMs: number;
  readonly onRevoke: (delegation: Delegation) => void;
}

/** The width of the row action, "Revoke delegation". */
const ACTIONS_WIDTH = 144;
/** The grid's width at 1440 px: the viewport less the navigation rail, the two gutters and the panel's border. */
export const GRID_WIDTH_1440 = 1158;

/** SCREENS §15.7 grid (T-PLT-21 columns), with the delegator: the list holds what was given and received. */
export function delegationColumns({
  membershipId,
  nowMs,
  onRevoke,
}: DelegationColumnOptions): readonly GridColumn<Delegation>[] {
  return [
    {
      id: "delegate",
      header: t("approvals.delegations.column.delegate"),
      kind: "user",
      value: (delegation) => delegation.delegate.display_name,
      width: 144,
    },
    {
      id: "delegator",
      header: t("approvals.delegations.column.delegator"),
      kind: "user",
      value: (delegation) => delegation.delegator.display_name,
      width: 144,
    },
    {
      id: "permissions",
      header: t("approvals.delegations.column.permissions"),
      kind: "text",
      value: (delegation) => formatList(delegation.permissions.map(permissionLabel), "unit"),
      width: 200,
    },
    {
      id: "valid_from",
      header: t("approvals.delegations.column.validFrom"),
      kind: "date",
      value: (delegation) => timestampDate(delegation.valid_from),
      sortKey: "valid_from",
      // The label with its sort mark and the column menu button.
      width: 136,
    },
    {
      id: "valid_to",
      header: t("approvals.delegations.column.validTo"),
      kind: "date",
      value: (delegation) => timestampDate(delegation.valid_to),
      sortKey: "valid_to",
      width: 128,
    },
    {
      id: "reason",
      header: t("approvals.delegations.column.reason"),
      kind: "text",
      value: (delegation) => delegation.reason,
      width: 144,
    },
    {
      id: "status",
      header: t("approvals.delegations.column.status"),
      kind: "status",
      value: (delegation) => STATUS_WORD[delegationStatus(delegation, nowMs)],
      render: (delegation) => (
        <StatusChip status={STATUS_WORD[delegationStatus(delegation, nowMs)]} />
      ),
      width: 120,
    },
    {
      id: "created_at",
      header: t("approvals.delegations.column.createdAt"),
      kind: "timestamp",
      value: (delegation) => delegation.created_at,
      sortKey: "created_at",
      // An instant with the cell padding is 186 px; the kit's default is 176.
      width: 192,
    },
    {
      id: "actions",
      header: t("approvals.delegations.column.actions"),
      kind: "actions",
      value: () => null,
      render: (delegation) =>
        revocable(delegation, membershipId, nowMs) ? (
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              onRevoke(delegation);
            }}
          >
            {t("approvals.delegations.revoke")}
          </Button>
        ) : null,
      width: ACTIONS_WIDTH,
    },
  ];
}

/**
 * The layout of the grid: the columns in the order of SCREENS §15.7 with the row action pinned to the
 * end, so "Revoke delegation" stays in view. At 1440 px the columns from Delegate to Status fit beside
 * it; "Created at" follows on scrolling.
 */
export function delegationColumnState(columns: readonly GridColumn<Delegation>[]): GridColumnState {
  return { ...initialColumnState(columns), pinned: { start: [], end: ["actions"] } };
}

/** The summed width of the columns from the first through `lastId`, without the pinned row action. */
export function scrolledWidth(columns: readonly GridColumn<Delegation>[], lastId: string): number {
  const end = columns.findIndex((column) => column.id === lastId);
  return columns
    .slice(0, end + 1)
    .filter((column) => column.id !== "actions")
    .reduce((sum, column) => sum + (column.width ?? DEFAULT_WIDTH[column.kind]), 0);
}

// docs/dev-guide.md DG-FE-06: the fields of "New delegation" and of "Revoke delegation" and the members
// of the body each sends. The API's finding on a permission of the list names `permissions[<index>]`
// (T-PLT-21): it stands under the list.
const DELEGATION_MEMBERS = {
  delegate: ["delegate_membership_id"],
  permissions: ["permissions"],
  validFrom: ["valid_from"],
  validTo: ["valid_to"],
  reason: ["reason"],
} as const;
const REVOKE_MEMBERS = { reason: ["reason"] } as const;

/** SCR-PERM-01 for RT-58: any approval permission. */
function DelegationsAccessLimited() {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("approvals.delegations.access.area") })}
      description={t("settings.access.description", {
        permission: t("approvals.delegations.access.permission"),
      })}
    />
  );
}

interface NewDelegationDrawerProps {
  readonly me: Me;
  readonly onClose: () => void;
  readonly onCreated: (delegation: Delegation) => void;
}

/** SCREENS §15.7 "New delegation". */
function NewDelegationDrawer({ me, onClose, onCreated }: NewDelegationDrawerProps) {
  const formId = useId();
  const permissionsId = useId();
  const permissionsErrorId = useId();
  const choices = useQuery({ queryKey: delegateChoicesKey(), queryFn: fetchDelegateChoices });
  const access = useAccess();
  const own = useMemo(() => ownApprovalPermissions(access), [access]);
  // The window opens today, the current day in platform time.
  const today = utcDateOf(Date.now());
  const [delegate, setDelegate] = useState<string | null>(null);
  const [chosen, setChosen] = useState<readonly string[]>([]);
  const [fromText, setFromText] = useState(() => formatDate(today));
  const [toText, setToText] = useState("");
  const [validFrom, setValidFrom] = useState<string | null>(today);
  const [validTo, setValidTo] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const create = useCommand<Delegation>({
    method: "POST",
    path: DELEGATIONS_PATH,
    invalidates: [EVERY_DELEGATION],
  });

  const problem = create.problem;
  const placed = useMemo(() => placeProblem(problem, DELEGATION_MEMBERS), [problem]);
  const touch = () => setDirty(true);
  // The viewer is not a choice: a member delegates to another member (SCREENS §15.7).
  const options = (choices.data ?? [])
    .filter((member) => member.id !== me.active_membership_id)
    .map((member) => ({ value: member.id, label: `${member.display_name} · ${member.email}` }));

  const required = t("approvals.delegations.required");
  const errors = {
    delegate: placed.fields.delegate ?? (attempted && delegate === null ? required : null),
    permissions:
      placed.fields.permissions ??
      (attempted && chosen.length === 0 ? t("approvals.delegations.permissionRequired") : null),
    validFrom: placed.fields.validFrom ?? (attempted && validFrom === null ? required : null),
    validTo:
      placed.fields.validTo ??
      (validFrom !== null && validTo !== null && validTo < validFrom
        ? t("approvals.delegations.order")
        : validFrom !== null && validTo !== null && !delegationWithinLimit(validFrom, validTo)
          ? t("approvals.delegations.limit")
          : attempted && validTo === null
            ? required
            : null),
  };
  const valid =
    delegate !== null &&
    chosen.length > 0 &&
    validFrom !== null &&
    validTo !== null &&
    validTo >= validFrom &&
    delegationWithinLimit(validFrom, validTo) &&
    reasonError(reason) === null;

  const send = async () => {
    if (delegate === null || validFrom === null || validTo === null) {
      return;
    }
    const body: DelegationCreate = {
      delegate_membership_id: delegate,
      permissions: [...chosen],
      // DS-I18N-08 (R-59): a window of whole days in platform time, its last day included.
      valid_from: dayStartInstant(validFrom),
      valid_to: dayEndInstant(validTo),
      reason: reason.trim(),
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onCreated(outcome.data);
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (create.pending || !valid) {
      return;
    }
    void send();
  };
  const toggle = (code: string, checked: boolean) => {
    touch();
    setChosen((current) =>
      checked
        ? own.filter((item) => item === code || current.includes(item))
        : current.filter((item) => item !== code),
    );
  };

  return (
    <>
      <Drawer
        open
        title={t("approvals.delegations.new")}
        initialFocus="field"
        dirty={dirty}
        submitting={create.pending}
        banner={
          problem === null || problem.slug === STEP_UP_REQUIRED_SLUG ? null : (
            <RefusalBanner problem={problem} placed={placed} />
          )
        }
        primaryAction={{ label: t("approvals.delegations.create"), form: formId }}
        onClose={onClose}
      >
        <form
          id={formId}
          noValidate
          data-testid="SF-12-drawer-delegation"
          onSubmit={submit}
          className="flex flex-col gap-4"
        >
          <Field
            name="delegation_delegate"
            label={t("approvals.delegations.column.delegate")}
            required
            help={t("approvals.delegations.delegateHelp")}
            error={errors.delegate}
          >
            {(control) => (
              <Combobox
                control={control}
                options={options}
                value={delegate}
                invalid={errors.delegate !== null}
                onChange={(value) => {
                  touch();
                  setDelegate(value);
                }}
              />
            )}
          </Field>
          <fieldset
            aria-describedby={errors.permissions === null ? permissionsId : permissionsErrorId}
            className="flex flex-col gap-2"
          >
            <legend className="text-body-sm font-medium text-fg-1">
              {t("approvals.delegations.column.permissions")}
            </legend>
            <p id={permissionsId} className="text-body-sm text-fg-3">
              {t("approvals.delegations.permissionsHelp")}
            </p>
            {errors.permissions === null ? null : (
              <p
                id={permissionsErrorId}
                className="flex items-start gap-1 text-body-sm text-negative-fg"
              >
                <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
                {errors.permissions}
              </p>
            )}
            {own.map((code) => (
              <label key={code} className="flex items-start gap-2 text-body-sm text-fg-1">
                <input
                  type="checkbox"
                  name="delegation_permissions"
                  value={code}
                  checked={chosen.includes(code)}
                  onChange={(event) => toggle(code, event.target.checked)}
                  className="mt-0.5 size-4 shrink-0"
                />
                {permissionLabel(code)}
              </label>
            ))}
          </fieldset>
          <div className="flex flex-wrap gap-4">
            <Field
              name="delegation_valid_from"
              label={t("approvals.delegations.column.validFrom")}
              required
              width="date"
              error={errors.validFrom}
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={fromText}
                  onChange={(text) => {
                    touch();
                    setFromText(text);
                  }}
                  onValue={setValidFrom}
                  invalid={errors.validFrom !== null}
                />
              )}
            </Field>
            <Field
              name="delegation_valid_to"
              label={t("approvals.delegations.column.validTo")}
              required
              width="date"
              error={errors.validTo}
            >
              {(control) => (
                <DateInput
                  control={control}
                  value={toText}
                  onChange={(text) => {
                    touch();
                    setToText(text);
                  }}
                  onValue={setValidTo}
                  invalid={errors.validTo !== null}
                />
              )}
            </Field>
          </div>
          <ReasonField
            name="delegation_reason"
            label={t("approvals.delegations.column.reason")}
            value={reason}
            onChange={(value) => {
              touch();
              setReason(value);
            }}
            showError={attempted}
            error={placed.fields.reason}
          />
        </form>
      </Drawer>
      {stepUp ? (
        <StepUpModal
          onCancel={() => setStepUp(false)}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

interface RevokeDialogProps {
  readonly delegation: Delegation;
  readonly onClose: () => void;
  readonly onRevoked: (delegation: Delegation) => void;
}

/** SCREENS §15.7 "Revoke delegation": a confirmation with a reason. */
function RevokeDialog({ delegation, onClose, onRevoked }: RevokeDialogProps) {
  const formId = useId();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const revoke = useCommand<Delegation>({
    method: "POST",
    path: revokePath(delegation.id),
    invalidates: [EVERY_DELEGATION],
  });
  const problem = revoke.problem;
  const placed = useMemo(() => placeProblem(problem, REVOKE_MEMBERS), [problem]);

  const send = async () => {
    const outcome = await revoke.submit({ reason: reason.trim() } satisfies DelegationRevoke);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onRevoked(outcome.data);
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (revoke.pending || reasonError(reason) !== null) {
      return;
    }
    void send();
  };

  return (
    <>
      <Modal
        open
        variant="confirmation"
        title={t("approvals.delegations.revokeTitle", { name: delegation.delegate.display_name })}
        description={t("approvals.delegations.revokeDescription", {
          name: delegation.delegate.display_name,
        })}
        primaryAction={{
          label: t("approvals.delegations.revoke"),
          destructive: true,
          form: formId,
        }}
        submitting={revoke.pending}
        onClose={onClose}
        testId="SF-12-dialog-revoke"
      >
        <form id={formId} noValidate onSubmit={submit} className="flex flex-col gap-3 pb-1">
          {problem === null || problem.slug === STEP_UP_REQUIRED_SLUG ? null : (
            <RefusalBanner problem={problem} placed={placed} />
          )}
          <ReasonField
            name="revoke_reason"
            label={t("approvals.delegations.column.reason")}
            value={reason}
            onChange={setReason}
            showError={attempted}
            error={placed.fields.reason}
          />
        </form>
      </Modal>
      {stepUp ? (
        <StepUpModal
          onCancel={() => setStepUp(false)}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

function DelegationsPage({ me }: { readonly me: Me }) {
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<Delegation | null>(null);
  // The statuses are those of the moment the page was read.
  const [nowMs] = useState(() => Date.now());
  const membershipId = me.active_membership_id;
  const columns = useMemo(
    () => delegationColumns({ membershipId, nowMs, onRevoke: setRevoking }),
    [membershipId, nowMs],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(() =>
    delegationColumnState(columns),
  );
  const source: GridSource<Delegation> = {
    queryKey: delegationsKey(),
    fetchPage: fetchDelegationsPage,
  };
  // API-R-09 has no read of the members a delegation may name: the choices are `GET /users`.
  const directory = useAccess().holdsAnywhere(USER_MANAGE_PERMISSION);
  const add = () => setCreating(true);

  return (
    <>
      <div className="flex justify-end">
        <Button
          variant="primary"
          disabledReason={directory ? undefined : t("approvals.delegations.directoryRequired")}
          onClick={add}
        >
          {t("approvals.delegations.new")}
        </Button>
      </div>
      <div className="flex flex-col">
        <DataGrid<Delegation>
          name="delegations"
          title={t("approvals.tabs.delegations")}
          errorTitle={t("approvals.delegations.loadError")}
          countLabel={(count, formatted) => t("approvals.delegations.count", { count, formatted })}
          columns={columns}
          columnState={columnState}
          onColumnStateChange={setColumnState}
          source={source}
          rowKey={(delegation) => delegation.id}
          rowLabel={(delegation) => delegation.delegate.display_name}
          testIdPrefix="SF-12"
          emptyState={
            <div data-testid="SF-12-empty-delegations">
              <EmptyState
                title={t("approvals.delegations.empty.title")}
                description={t("approvals.delegations.empty.description")}
                action={
                  directory ? { label: t("approvals.delegations.new"), onAction: add } : undefined
                }
              />
            </div>
          }
        />
      </div>
      {creating ? (
        <NewDelegationDrawer
          me={me}
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            toast.show({
              tone: "positive",
              message: t("approvals.delegations.created", {
                name: created.delegate.display_name,
                date: formatDate(timestampDate(created.valid_to)),
              }),
            });
          }}
        />
      ) : null}
      {revoking === null ? null : (
        <RevokeDialog
          delegation={revoking}
          onClose={() => setRevoking(null)}
          onRevoked={(revoked) => {
            setRevoking(null);
            toast.show({
              tone: "positive",
              message: t("approvals.delegations.revoked", {
                name: revoked.delegate.display_name,
              }),
            });
          }}
        />
      )}
    </>
  );
}

export function Delegations() {
  const me = useMe();
  const access = useAccess();
  let body;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("approvals.tabs.delegations")} shape="rows" count={6} />;
  } else if (!holdsApprovalPermission(access)) {
    body = <DelegationsAccessLimited />;
  } else {
    body = <DelegationsPage me={me.data} />;
  }
  // The page keeps its natural height, so an empty grid shows its empty state under the header row.
  return (
    <div data-testid="SF-12-page" className="flex flex-col gap-3">
      <ApprovalsHeader />
      {body}
    </div>
  );
}
