// SF-16 Integrations (SCREENS §14.1 to §14.9; §0.3 SCR-IA-02; §0.4 RT-48; §0.6 SCR-PERM-01, SCR-PERM-05; §0.8
// T-INT-01, E-72; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-19, DS-CMP-21, DS-CMP-23, DS-FMT-17; 04
// API-R-45 `GET, POST /integrations`, `PATCH /integrations/{id}`; REQ-INT-006; BR-INT-01; BUILD_SPEC DIN-18).
// The Data frame with the `h1` "Integrations", "<n> connections" and "Add connection"; the DataGrid
// "Integrations" with Connection (link), Adapter with the outline chip "Mock" for an in-process mock
// adapter, Direction, Entities, Status, Last test, Last sync, Control totals and Code (hidden). The grid
// shows what the API answers: "Reconciled" and "Difference" are the status of the newest sync run. The
// drawer "Add connection" (and "Edit connection" on SF-16:connection) holds Adapter, Name, Code,
// Direction, Entities, Base URL, Credential reference and Settings; a new connection starts Disabled. The
// credential reference is the name of a secret: the secret itself is never typed, stored or shown.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

import { useOpenMembership } from "../../app/shell/open-workspace";
import { DataGrid } from "../../components/data-grid/DataGrid";
import {
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
import { controlClass, Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Select } from "../../components/form/Select";
import { Plus, X } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, OutlineChip, StatusChip, type StatusWord } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { useAllEntities } from "../../lib/api/queries/entities";
import {
  type Adapter,
  ADAPTERS,
  type Connection,
  type ConnectionCreate,
  connectionPath,
  connectionRoute,
  connectionsKey,
  type ConnectionUpdate,
  DEFAULT_DIRECTION,
  type Direction,
  DIRECTIONS,
  EVERY_INTEGRATION,
  fetchConnectionsPage,
  INTEGRATION_MANAGE_PERMISSION,
  INTEGRATIONS_PATH,
  isMock,
  SANDBOX_ADAPTERS,
  SANDBOX_DIRECTIONS,
  secretNamespaceOf,
  type SyncRun,
  type SyncRunKind,
  type SyncRunStatus,
} from "../../lib/api/queries/integrations";
import {
  fetchActiveMembers,
  membersKey,
  USER_MANAGE_PERMISSION,
} from "../../lib/api/queries/exceptions";
import { useMe } from "../../lib/api/queries/me";
import { type Entity, rowIfMatch } from "../../lib/api/queries/tenant";
import { placeProblem } from "../../lib/api/refusals";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { StepUpModal } from "../settings/profile";
import { DataPageHeader } from "./imports";

/** SCREENS §14.3 column 9: hidden by default. */
export const HIDDEN_BY_DEFAULT: readonly string[] = ["code"];
const STEP_UP_REQUIRED_SLUG = "mfa-step-up-required";
const NAME_MAX = 200;
const CODE_MAX = 64;

export function adapterLabel(adapter: Adapter): string {
  return t(`data.integrations.adapter.${adapter}`);
}

export function directionLabel(direction: Direction): string {
  return t(`data.integrations.direction.${direction}`);
}

/** SCREENS §14.3 sync runs grid column 2. */
export function kindLabel(kind: SyncRunKind): string {
  return t(`data.integrations.kind.${kind}`);
}

/** SCR-PERM-01 for `integration.manage` (SCREENS §14.6 "No permission"). */
export function IntegrationsAccessLimited() {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("data.access.integrations") })}
      description={t("settings.access.description", {
        permission: t("data.integrations.access.permission"),
      })}
    />
  );
}

/** SCREENS §0.8 T-INT-01: "Active" or "Disabled". */
export function ConnectionStatusChip({ status }: { readonly status: Connection["status"] }) {
  const chip = chipFor("T-INT-01", status);
  return chip === null ? null : <StatusChip status={chip.status} />;
}

/** SCREENS §0.8 E-72: the chip of a sync run status. */
export function SyncStatusChip({ status }: { readonly status: SyncRunStatus }) {
  const chip = chipFor("E-72", status);
  return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
}

/**
 * SCREENS §14.3 "Result" and "Control totals": "Reconciled" for a run that succeeded, "Difference" for a
 * control total mismatch, no value otherwise. The run's status says which; nothing is compared here.
 */
export function totalsWord(status: SyncRunStatus): StatusWord | null {
  if (status === "SUCCEEDED") {
    return "Reconciled";
  }
  return status === "CONTROL_TOTAL_MISMATCH" ? "Difference" : null;
}

/**
 * The status a run's result reads: none for a run that recorded no totals on either side (a test, a
 * run that failed before it loaded anything), which has nothing to reconcile. Presence only: the two
 * sides are never compared here.
 */
export function totalsStatus(
  run: Pick<SyncRun, "status" | "source_totals" | "loaded_totals">,
): SyncRunStatus | null {
  return run.source_totals === null && run.loaded_totals === null ? null : run.status;
}

export function TotalsChip({ status }: { readonly status: SyncRunStatus | null }) {
  const word = status === null ? null : totalsWord(status);
  return word === null ? <NoValue /> : <StatusChip status={word} />;
}

/** SCREENS §14.3 column 4: the codes of `entity_ids`, "All entities" when empty. */
export function entitiesText(
  entityIds: readonly string[],
  entities: readonly Entity[] | undefined,
): string | null {
  if (entityIds.length === 0) {
    return t("data.integrations.allEntities");
  }
  if (entities === undefined) {
    return null;
  }
  const codes = new Map(entities.map((entity) => [entity.id, entity.code]));
  // An entity outside the viewer's scope has no code here and is counted, never shown by id.
  const known = entityIds.flatMap((id) => codes.get(id) ?? []);
  const hidden = entityIds.length - known.length;
  if (hidden === 0) {
    return known.join(", ");
  }
  const counted = { count: hidden, formatted: formatNumber(hidden, { kind: "count" }) };
  return known.length === 0
    ? t("data.integrations.entitiesOutOfScope", counted)
    : t("data.integrations.entitiesAndOthers", { ...counted, codes: known.join(", ") });
}

function mono(text: string): ReactNode {
  return <span className="truncate font-mono text-mono-sm text-fg-1">{text}</span>;
}

/** A chip and an instant side by side (SCREENS §14.3 columns 6 and 7). */
function ChipAndTime({ chip, at }: { readonly chip: ReactNode; readonly at: string | null }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      {chip}
      {at === null ? null : (
        <time dateTime={at} className="num truncate text-fg-2" data-volatile="">
          {formatTimestamp(at)}
        </time>
      )}
    </span>
  );
}

/** SCREENS §14.3 connections grid. */
export function connectionColumns(
  entities: readonly Entity[] | undefined,
): readonly GridColumn<Connection>[] {
  return [
    {
      id: "name",
      header: t("data.integrations.column.connection"),
      kind: "identifier",
      value: (item) => item.name,
      href: (item) => connectionRoute(item.id),
      render: (item) => (
        <Link
          to={connectionRoute(item.id)}
          tabIndex={-1}
          className="truncate font-medium text-accent-fg hover:text-accent-fg-hover hover:underline"
        >
          {item.name}
        </Link>
      ),
      sortKey: "name",
      width: 240,
    },
    {
      id: "adapter",
      header: t("data.integrations.column.adapter"),
      kind: "text",
      value: (item) => adapterLabel(item.adapter),
      render: (item) => (
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate">{adapterLabel(item.adapter)}</span>
          {isMock(item) ? <OutlineChip label={t("data.integrations.mock")} /> : null}
        </span>
      ),
      width: 208,
    },
    {
      id: "direction",
      header: t("data.integrations.column.direction"),
      kind: "text",
      value: (item) => directionLabel(item.direction),
      width: 112,
    },
    {
      id: "entities",
      header: t("data.integrations.column.entities"),
      kind: "text",
      value: (item) => entitiesText(item.entity_ids, entities),
      render: (item) => {
        const text = entitiesText(item.entity_ids, entities);
        if (text === null) {
          return <NoValue />;
        }
        return item.entity_ids.length === 0 ? <span className="truncate">{text}</span> : mono(text);
      },
      width: 176,
    },
    {
      id: "status",
      header: t("data.integrations.column.status"),
      kind: "status",
      value: (item) => item.status,
      render: (item) => <ConnectionStatusChip status={item.status} />,
      width: 120,
    },
    {
      id: "last_test",
      header: t("data.integrations.column.lastTest"),
      kind: "status",
      value: (item) => item.last_test_at,
      render: (item) =>
        item.last_test_result === null ? (
          <NoValue />
        ) : (
          <ChipAndTime
            chip={
              <StatusChip status={item.last_test_result === "SUCCESS" ? "Succeeded" : "Failed"} />
            }
            at={item.last_test_at}
          />
        ),
      width: 296,
    },
    {
      id: "last_sync",
      header: t("data.integrations.column.lastSync"),
      kind: "status",
      value: (item) => item.last_sync_run?.finished_at ?? null,
      render: (item) =>
        item.last_sync_run === null ? (
          <NoValue />
        ) : (
          <ChipAndTime
            chip={<SyncStatusChip status={item.last_sync_run.status} />}
            at={item.last_sync_run.finished_at}
          />
        ),
      width: 296,
    },
    {
      id: "control_totals",
      header: t("data.integrations.column.controlTotals"),
      kind: "status",
      value: (item) => item.last_sync_run?.status ?? null,
      render: (item) => <TotalsChip status={item.last_sync_run?.status ?? null} />,
      width: 152,
    },
    {
      id: "code",
      header: t("data.integrations.column.code"),
      kind: "text",
      value: (item) => item.code,
      render: (item) => mono(item.code),
      sortKey: "code",
      width: 160,
    },
  ];
}

interface SettingRow {
  readonly id: number;
  readonly key: string;
  readonly text: string;
  /** The stored value of an existing setting, kept as it is while its text is unchanged. */
  readonly original?: unknown;
}

function settingText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function settingRows(config: Readonly<Record<string, unknown>>): SettingRow[] {
  return Object.keys(config)
    .sort()
    .map((key, index) => ({
      id: index,
      key,
      text: settingText(config[key]),
      original: config[key],
    }));
}

/** The `config` the rows stand for; a row without a key is left out. */
function configOf(rows: readonly SettingRow[]): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (key !== "") {
      config[key] =
        row.original !== undefined && settingText(row.original) === row.text
          ? row.original
          : row.text;
    }
  }
  return config;
}

export interface ConnectionDrawerProps {
  /** The connection to edit; none adds a connection. */
  readonly connection?: Connection | undefined;
  /** `secretNamespace` of the workspace: the fixed beginning of every credential reference. */
  readonly namespace: string;
  /**
   * The open workspace is a sandbox (SB-R-08): "Add connection" offers the adapters and the direction
   * `POST /integrations` accepts there, and says why the others are not offered.
   */
  readonly sandbox?: boolean;
  readonly onClose: () => void;
  readonly onSaved: (connection: Connection) => void;
}

/** SCREENS §14.4 "Add connection" and "Edit connection". */
// docs/dev-guide.md DG-FE-06: the fields of the connection drawer and the members of the body each
// sends; a setting is a key of `config`.
const CONNECTION_MEMBERS = {
  adapter: ["adapter"],
  name: ["name"],
  code: ["code"],
  direction: ["direction"],
  entities: ["entity_ids"],
  owner: ["owner_membership_id"],
  baseUrl: ["base_url"],
  secretRef: ["secret_ref"],
  settings: ["config"],
} as const;
// The adapter, the code and the direction are fixed once a connection exists: the edit drawer shows no
// field for them.
const CONNECTION_MEMBERS_OF_EDIT = {
  ...CONNECTION_MEMBERS,
  adapter: [],
  code: [],
  direction: [],
} as const;

export function ConnectionDrawer({
  connection,
  namespace,
  sandbox = false,
  onClose,
  onSaved,
}: ConnectionDrawerProps) {
  const adapters = sandbox ? SANDBOX_ADAPTERS : ADAPTERS;
  const directions = sandbox ? SANDBOX_DIRECTIONS : DIRECTIONS;
  const formId = useId();
  const settingsId = useId();
  const namespaceId = useId();
  const entities = useAllEntities();
  const editing = connection !== undefined;
  const me = useMe();
  const access = useAccess();
  const members = useQuery({
    queryKey: membersKey(),
    queryFn: fetchActiveMembers,
    enabled: access.holdsAnywhere(USER_MANAGE_PERMISSION),
  });
  const [owner, setOwner] = useState(
    connection === undefined ? "automatic" : (connection.owner_membership_id ?? "unassigned"),
  );
  const ownerOptions = new Map<string, string>([
    ["unassigned", t("data.integrations.owner.unassigned")],
  ]);
  if (!editing) ownerOptions.set("automatic", t("data.integrations.owner.automatic"));
  if (connection?.owner_membership_id)
    ownerOptions.set(connection.owner_membership_id, t("data.integrations.owner.current"));
  if (me.data?.active_membership_id)
    ownerOptions.set(me.data.active_membership_id, me.data.user.display_name);
  for (const member of members.data ?? []) ownerOptions.set(member.id, member.display_name);

  const [adapter, setAdapter] = useState<Adapter | null>(connection?.adapter ?? null);
  const [name, setName] = useState(connection?.name ?? "");
  const [code, setCode] = useState(connection?.code ?? "");
  const [direction, setDirection] = useState<Direction | null>(connection?.direction ?? null);
  const [entityIds, setEntityIds] = useState<readonly string[]>(connection?.entity_ids ?? []);
  const [baseUrl, setBaseUrl] = useState(connection?.base_url ?? "");
  // T-INT-01 rev 1.108: the field holds what follows the workspace's namespace. A stored reference
  // outside the namespace is shown as it is and is sent only when the field is changed.
  const storedRef = connection?.secret_ref ?? null;
  const storedOutside = storedRef !== null && !storedRef.startsWith(namespace);
  const [secretRest, setSecretRest] = useState(
    storedRef === null || storedOutside ? "" : storedRef.slice(namespace.length),
  );
  const [secretChanged, setSecretChanged] = useState(false);
  const [settings, setSettings] = useState<readonly SettingRow[]>(() =>
    settingRows(connection?.config ?? {}),
  );
  const [attempted, setAttempted] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const save = useCommand<Connection>(
    connection === undefined
      ? { method: "POST", path: INTEGRATIONS_PATH, invalidates: [EVERY_INTEGRATION] }
      : {
          method: "PATCH",
          path: connectionPath(connection.id),
          ifMatch: rowIfMatch(connection.row_version),
          invalidates: [EVERY_INTEGRATION],
        },
  );

  const touch = () => setDirty(true);
  const problem = save.problem;
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof CONNECTION_MEMBERS>(
        problem,
        editing ? CONNECTION_MEMBERS_OF_EDIT : CONNECTION_MEMBERS,
      ),
    [problem, editing],
  );
  const required = (value: string) =>
    attempted && value.trim() === "" ? t("data.integrations.drawer.required") : null;
  const errors = {
    adapter:
      attempted && adapter === null
        ? t("data.integrations.drawer.required")
        : placed.fields.adapter,
    name:
      required(name) ??
      (attempted && name.trim().length > NAME_MAX
        ? t("data.integrations.drawer.tooLong", { count: NAME_MAX })
        : placed.fields.name),
    code:
      required(code) ??
      (attempted && code.trim().length > CODE_MAX
        ? t("data.integrations.drawer.tooLong", { count: CODE_MAX })
        : placed.fields.code),
    direction:
      attempted && direction === null
        ? t("data.integrations.drawer.required")
        : placed.fields.direction,
    entities: placed.fields.entities,
    owner: placed.fields.owner,
    baseUrl: placed.fields.baseUrl,
    secretRef:
      placed.fields.secretRef ??
      (storedOutside && !secretChanged
        ? t("data.integrations.secretOutside", { reference: storedRef })
        : null),
    settings: placed.fields.settings,
  };
  const valid =
    adapter !== null &&
    direction !== null &&
    name.trim() !== "" &&
    name.trim().length <= NAME_MAX &&
    code.trim() !== "" &&
    code.trim().length <= CODE_MAX;

  const send = async () => {
    if (adapter === null || direction === null) {
      return;
    }
    const rest = secretRest.trim();
    const shared = {
      name: name.trim(),
      entity_ids: [...entityIds],
      ...(owner === "automatic" ||
      (editing && owner === (connection.owner_membership_id ?? "unassigned"))
        ? {}
        : { owner_membership_id: owner === "unassigned" ? null : owner }),
      base_url: baseUrl.trim() === "" ? null : baseUrl.trim(),
      ...(storedOutside && !secretChanged
        ? {}
        : { secret_ref: rest === "" ? null : `${namespace}${rest}` }),
      config: configOf(settings),
    };
    const outcome = await save.submit(
      editing
        ? (shared satisfies ConnectionUpdate)
        : ({ ...shared, adapter, code: code.trim(), direction } satisfies ConnectionCreate),
    );
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onSaved(outcome.data);
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (save.pending || !valid) {
      return;
    }
    void send();
  };

  // SCR-ST-09: after a 412 the banner says that the connection changed since it was opened. A refusal
  // that asks for the step-up is answered by its modal, not by a banner.
  const banner = (
    <RefusalBanner
      problem={problem?.slug === STEP_UP_REQUIRED_SLUG ? null : problem}
      placed={placed}
      conflict={save.banner}
    />
  );

  const entityOptions = (entities.data ?? []).map((entity) => ({
    value: entity.id,
    label: `${entity.code} · ${entity.name}`,
  }));
  const updateSetting = (id: number, change: Partial<Pick<SettingRow, "key" | "text">>) => {
    touch();
    setSettings((rows) => rows.map((row) => (row.id === id ? { ...row, ...change } : row)));
  };

  return (
    <>
      <Drawer
        open
        title={t(editing ? "data.integrations.drawer.editTitle" : "data.integrations.add")}
        dirty={dirty}
        submitting={save.pending}
        banner={banner}
        primaryAction={{ label: t("data.integrations.drawer.save"), form: formId }}
        onClose={onClose}
      >
        <form
          id={formId}
          noValidate
          data-testid="SF-16-drawer-connection"
          onSubmit={submit}
          className="flex flex-col gap-4"
        >
          {connection === undefined ? (
            <Field
              name="connection_adapter"
              label={t("data.integrations.drawer.adapter")}
              required
              help={
                sandbox
                  ? `${t("data.integrations.drawer.adapterHelp")} ${t("data.integrations.drawer.sandboxHelp")}`
                  : t("data.integrations.drawer.adapterHelp")
              }
              error={errors.adapter}
            >
              {(control) => (
                <Select
                  control={control}
                  options={adapters.map((value) => ({ value, label: adapterLabel(value) }))}
                  value={adapter}
                  invalid={errors.adapter !== null}
                  placeholder={t("data.integrations.drawer.adapterPlaceholder")}
                  onChange={(value) => {
                    touch();
                    setAdapter(value);
                    // SCREENS §14.4: the direction defaults per adapter and stays editable; in a
                    // sandbox the default is one the workspace takes (NetSuite: Outbound, not Both).
                    const usual = DEFAULT_DIRECTION[value];
                    setDirection(directions.includes(usual) ? usual : (directions[0] ?? usual));
                  }}
                />
              )}
            </Field>
          ) : (
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-body-sm">
              <dt className="text-fg-3">{t("data.integrations.drawer.adapter")}</dt>
              <dd className="text-fg-1">{adapterLabel(connection.adapter)}</dd>
              <dt className="text-fg-3">{t("data.integrations.drawer.code")}</dt>
              <dd className="font-mono text-mono-sm text-fg-1">{connection.code}</dd>
              <dt className="text-fg-3">{t("data.integrations.drawer.direction")}</dt>
              <dd className="text-fg-1">{directionLabel(connection.direction)}</dd>
            </dl>
          )}
          <Field
            name="connection_name"
            label={t("data.integrations.drawer.name")}
            required
            error={errors.name}
          >
            {(control) => (
              <input
                {...control}
                type="text"
                autoComplete="off"
                value={name}
                onChange={(event) => {
                  touch();
                  setName(event.target.value);
                }}
                className={controlClass(errors.name !== null)}
              />
            )}
          </Field>
          {editing ? null : (
            <>
              <Field
                name="connection_code"
                label={t("data.integrations.drawer.code")}
                required
                help={t("data.integrations.drawer.codeHelp")}
                error={errors.code}
              >
                {(control) => (
                  <input
                    {...control}
                    type="text"
                    autoComplete="off"
                    spellCheck={false}
                    value={code}
                    onChange={(event) => {
                      touch();
                      setCode(event.target.value);
                    }}
                    className={`${controlClass(errors.code !== null)} font-mono`}
                  />
                )}
              </Field>
              <Field
                name="connection_direction"
                label={t("data.integrations.drawer.direction")}
                required
                error={errors.direction}
              >
                {(control) => (
                  <Select
                    control={control}
                    options={directions.map((value) => ({ value, label: directionLabel(value) }))}
                    value={direction}
                    invalid={errors.direction !== null}
                    placeholder={t("data.integrations.drawer.directionPlaceholder")}
                    onChange={(value) => {
                      touch();
                      setDirection(value);
                    }}
                  />
                )}
              </Field>
            </>
          )}
          <Field
            name="connection_entities"
            label={t("data.integrations.drawer.entities")}
            help={t("data.integrations.drawer.entitiesHelp")}
            error={errors.entities}
          >
            {(control) => (
              <MultiSelect
                control={control}
                options={entityOptions}
                values={entityIds}
                invalid={errors.entities !== null}
                onChange={(values) => {
                  touch();
                  setEntityIds(values);
                }}
              />
            )}
          </Field>
          <Field
            name="connection_owner"
            label={t("data.integrations.owner.label")}
            help={t("data.integrations.owner.help")}
            error={errors.owner}
          >
            {(control) => (
              <Select
                control={control}
                options={[...ownerOptions].map(([value, label]) => ({ value, label }))}
                value={owner}
                invalid={errors.owner !== null}
                onChange={(value) => {
                  touch();
                  setOwner(value);
                }}
              />
            )}
          </Field>
          {owner === "unassigned" ? (
            <Banner tone="warning" title={t("data.integrations.owner.missing")} />
          ) : null}
          {members.isError ? <Banner tone="negative" title={members.error.message} /> : null}
          <Field
            name="connection_base_url"
            label={t("data.integrations.drawer.baseUrl")}
            help={t("data.integrations.drawer.baseUrlHelp")}
            error={errors.baseUrl}
          >
            {(control) => (
              <input
                {...control}
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={baseUrl}
                onChange={(event) => {
                  touch();
                  setBaseUrl(event.target.value);
                }}
                className={`${controlClass(errors.baseUrl !== null)} font-mono`}
              />
            )}
          </Field>
          <Field
            name="connection_secret_ref"
            label={t("data.integrations.drawer.secretRef")}
            help={t("data.integrations.secretHelp")}
            error={errors.secretRef}
          >
            {(control) => (
              <div className="flex flex-col">
                <span
                  id={namespaceId}
                  data-volatile=""
                  className="rounded-t-md border border-b-0 border-control bg-subtle px-2.5 py-1 font-mono text-mono-sm break-all text-fg-2"
                >
                  {namespace}
                </span>
                <input
                  {...control}
                  aria-describedby={[namespaceId, control["aria-describedby"]]
                    .filter((id) => id !== undefined)
                    .join(" ")}
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  value={secretRest}
                  onChange={(event) => {
                    touch();
                    setSecretChanged(true);
                    // A reference pasted whole keeps one prefix.
                    const value = event.target.value.trimStart();
                    setSecretRest(
                      value.startsWith(namespace) ? value.slice(namespace.length) : value,
                    );
                  }}
                  className={`${controlClass(errors.secretRef !== null)} rounded-t-none font-mono`}
                />
              </div>
            )}
          </Field>
          <fieldset aria-describedby={settingsId} className="flex flex-col gap-2">
            <legend className="text-body-sm font-medium text-fg-1">
              {t("data.integrations.drawer.settings")}
            </legend>
            <p id={settingsId} className="text-body-sm text-fg-3">
              {t("data.integrations.drawer.settingsHelp")}
            </p>
            {errors.settings === null ? null : (
              <p className="text-body-sm text-negative-fg">{errors.settings}</p>
            )}
            {settings.map((row, index) => (
              <div key={row.id} className="flex items-center gap-2">
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  aria-label={t("data.integrations.drawer.settingKey", { row: index + 1 })}
                  value={row.key}
                  onChange={(event) => updateSetting(row.id, { key: event.target.value })}
                  className={`${controlClass(false)} font-mono`}
                />
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  aria-label={t("data.integrations.drawer.settingValue", { row: index + 1 })}
                  value={row.text}
                  onChange={(event) => updateSetting(row.id, { text: event.target.value })}
                  className={`${controlClass(false)} font-mono`}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  icon={X}
                  aria-label={t("data.integrations.drawer.removeSetting", { row: index + 1 })}
                  onClick={() => {
                    touch();
                    setSettings((rows) => rows.filter((item) => item.id !== row.id));
                  }}
                />
              </div>
            ))}
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              className="self-start"
              onClick={() => {
                touch();
                setSettings((rows) => [
                  ...rows,
                  { id: Math.max(-1, ...rows.map((row) => row.id)) + 1, key: "", text: "" },
                ]);
              }}
            >
              {t("data.integrations.drawer.addSetting")}
            </Button>
          </fieldset>
        </form>
      </Drawer>
      {stepUp ? (
        <StepUpModal
          onCancel={() => {
            setStepUp(false);
          }}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

const DEFAULT_COLUMNS: GridColumnState = initialColumnState(
  connectionColumns(undefined),
  HIDDEN_BY_DEFAULT,
);

export function IntegrationsList() {
  const me = useMe();
  const access = useAccess();
  // The workspace is the session's: a sandbox copy holds its source's membership id.
  const open = useOpenMembership();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.integrations.title")} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(INTEGRATION_MANAGE_PERMISSION)) {
    body = <IntegrationsAccessLimited />;
  } else {
    return (
      <IntegrationsPage
        namespace={secretNamespaceOf(open)}
        sandbox={open?.tenant.kind === "sandbox"}
      />
    );
  }
  return (
    <div data-testid="SF-16-page" className="flex flex-col gap-4">
      <DataPageHeader title={t("data.integrations.title")} />
      {body}
    </div>
  );
}

interface IntegrationsPageProps {
  /** The workspace's namespace of the secret store; "Add connection" needs it. */
  readonly namespace: string | null;
  /** The open workspace is a sandbox: "Add connection" offers what it accepts (SB-R-08). */
  readonly sandbox: boolean;
}

function IntegrationsPage({ namespace, sandbox }: IntegrationsPageProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const entities = useAllEntities();
  const [adding, setAdding] = useState(false);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const columns = useMemo(() => connectionColumns(entities.data), [entities.data]);
  const [columnState, setColumnState] = useState<GridColumnState>(DEFAULT_COLUMNS);
  const source: GridSource<Connection> = {
    queryKey: connectionsKey(),
    fetchPage: fetchConnectionsPage,
  };
  const countLabel = (value: number) =>
    t("data.integrations.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  const add = () => setAdding(true);

  return (
    <div data-testid="SF-16-page" className="flex h-full min-h-0 flex-col gap-4">
      <DataPageHeader
        title={t("data.integrations.title")}
        count={total === undefined ? undefined : countLabel(total)}
        actions={
          <Button variant="primary" onClick={add}>
            {t("data.integrations.add")}
          </Button>
        }
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<Connection>
          name="connections"
          title={t("data.integrations.title")}
          titleVisible={false}
          errorTitle={t("data.integrations.loadError")}
          countLabel={(value, formatted) =>
            t("data.integrations.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(item) => item.id}
          rowLabel={(item) => item.name}
          rowHref={(item) => connectionRoute(item.id)}
          testIdPrefix="SF-16"
          rowTestKey={(item) => item.code}
          columnState={columnState}
          defaultColumnState={DEFAULT_COLUMNS}
          onColumnStateChange={setColumnState}
          onTotalChange={(next) => setTotal(next?.count)}
          emptyState={
            <div data-testid="SF-16-empty-connections">
              <EmptyState
                title={t("data.integrations.empty.title")}
                description={t("data.integrations.empty.description")}
                action={{ label: t("data.integrations.add"), onAction: add }}
              />
            </div>
          }
        />
      </div>
      {adding && namespace !== null ? (
        <ConnectionDrawer
          namespace={namespace}
          sandbox={sandbox}
          onClose={() => setAdding(false)}
          onSaved={(created) => {
            setAdding(false);
            toast.show({
              tone: "positive",
              message: t("data.integrations.added", { name: created.name }),
            });
            void navigate(connectionRoute(created.id));
          }}
        />
      ) : null}
    </div>
  );
}
