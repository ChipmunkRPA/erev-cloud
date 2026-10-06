// SF-16:developer API clients and webhooks (SCREENS_B §9.15; SCREENS §0.4 RT-93, §0.3 SB-R-05, SB-R-08,
// §0.7 SCR-PERM-01, SCR-PERM-05, SCR-ST-03, §0.4 E-97, E-103; DESIGN_SYSTEM DS-CMP-07, DS-CMP-09,
// DS-CMP-10, DS-CMP-11; 04 API-R-08, API-R-15, API-R-06 `GET /permissions`, API-R-53 `GET /openapi.json`;
// T-PLT-15, T-PLT-35, T-PLT-36; PRD ERR-24; REQ-PLT-033, REQ-PLT-034, REQ-PLT-037, REQ-OPS-016; CTL-037;
// BUILD_SPEC WEB-23). The Settings frame with the panel tabs "API clients" (`api_client.manage`),
// "Webhooks" (`webhook.manage`) and "OpenAPI" (either). API clients: the DataGrid, "New API client"
// (non-approval scopes grouped by area, entity scope, expiry defaulting to 365 days, rate limit
// defaulting to 600; SCR-PERM-05 step-up; then the one-time dialog "Client secret for <name>"),
// "Rotate secret" and "Revoke" (SB-R-05). Webhooks: the endpoints grid with "Activate"/"Deactivate"
// (SB-R-08 in a sandbox), "New webhook endpoint" with the one-time dialog "Signing secret for <URL>"
// (SB-R-08 in a sandbox too: an endpoint is created active and the server refuses it, 05 SBX-08),
// and the deliveries grid with the E-97 chips. OpenAPI: the definition lines and the document link.
// "Download inventory" (RPT-27) arrives with the item that builds the report (BS1-D-14).
//
// SCREENS_B rev 1.62: "Selected entities" is unavailable with its reason until the API admits an
// entity scope on an API client (item API-CLIENT-ENTITY-SCOPE-1), and a refusal's field errors show at
// the field whose member they name in the three forms of the screen (DS-CMP-21); a message that names
// no field of the form is listed in the banner.
import { type FormEvent, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useSearchParams } from "react-router";

import { sandboxTenantName, useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs, type TabItem } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  API_CLIENT_MANAGE_PERMISSION,
  API_CLIENTS_PATH,
  type ApiClient,
  type ApiClientCreate,
  apiClientCommandPath,
  type ApiClientSecret,
  apiClientsGridKey,
  clientTestKey,
  DEFAULT_RATE_LIMIT,
  defaultExpiry,
  type DeveloperPane,
  developerPaneOf,
  EVERY_API_CLIENT,
  expiryInstant,
  fetchApiClientsPage,
  maskSecret,
  OPENAPI_PATH,
  SCOPE_NOT_ALLOWED_SLUG,
  scopeGroups,
  shortClientId,
  STEP_UP_REQUIRED_SLUG,
  WEBHOOK_MANAGE_PERMISSION,
} from "../../lib/api/queries/api-clients";
import { useAllEntities } from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import { usePermissions } from "../../lib/api/queries/roles";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import {
  acceptableWebhookUrl,
  DELIVERY_STATUSES,
  deliveriesGridKey,
  endpointPath,
  endpointsGridKey,
  EVERY_DELIVERY,
  EVERY_WEBHOOK,
  fetchDeliveriesPage,
  fetchEndpointsPage,
  urlPrefix,
  useAllEndpoints,
  WEBHOOK_ENDPOINTS_PATH,
  WEBHOOK_EVENT_KINDS,
  type WebhookDelivery,
  type WebhookDeliveryStatus,
  type WebhookEndpoint,
  type WebhookEndpointCreate,
  type WebhookEndpointCreated,
} from "../../lib/api/queries/webhooks";
import { useFieldRefusals } from "../../lib/api/refusals";
import { formatDate, formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { permissionWords } from "../../lib/permission-words";
import { SettingsPageHeader } from "../settings/index";
import { StepUpModal } from "../settings/profile";

const PAGE_TEST_ID = "SF-16-developer-page";
const RATE_LIMIT_PATTERN = /^[1-9][0-9]*$/;

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

function noValue() {
  return <span className="text-fg-3">{NO_VALUE}</span>;
}

function count(key: string, value: number): string {
  return t(key, { count: value, formatted: formatNumber(value, { kind: "count" }) });
}

// ---------------------------------------------------------------------------------------------------
// Screen frame
// ---------------------------------------------------------------------------------------------------

export function DeveloperScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("developer.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (
    !access.holdsAnywhere(API_CLIENT_MANAGE_PERMISSION) &&
    !access.holdsForAll(WEBHOOK_MANAGE_PERMISSION)
  ) {
    // The webhooks of the workspace are read and managed by a holder for all entities alone.
    body = (
      <AccessLimited
        area={title}
        permissions={[API_CLIENT_MANAGE_PERMISSION, WEBHOOK_MANAGE_PERMISSION]}
        allEntities={
          access.holdsAnywhere(WEBHOOK_MANAGE_PERMISSION)
            ? { message: "developer.access.allEntities", permission: WEBHOOK_MANAGE_PERMISSION }
            : undefined
        }
      />
    );
  } else {
    return <DeveloperPage />;
  }
  return (
    <div data-testid={PAGE_TEST_ID} className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="developer" />
      {body}
    </div>
  );
}

/** SCREENS_B §9.15 tabs: a tab the member may not read renders disabled with its reason. */
export function developerTabs(access: Access): readonly TabItem[] {
  const canClients = access.holdsAnywhere(API_CLIENT_MANAGE_PERMISSION);
  const canWebhooks = access.holdsForAll(WEBHOOK_MANAGE_PERMISSION);
  return [
    {
      id: "api-clients",
      label: t("developer.pane.apiClients"),
      disabledReason: canClients
        ? undefined
        : t("developer.access.apiClients", {
            permission: permissionWords(API_CLIENT_MANAGE_PERMISSION),
          }),
    },
    {
      id: "webhooks",
      label: t("developer.pane.webhooks"),
      disabledReason: canWebhooks
        ? undefined
        : t(
            access.holdsAnywhere(WEBHOOK_MANAGE_PERMISSION)
              ? "developer.access.webhooksAllEntities"
              : "developer.access.webhooks",
            { permission: permissionWords(WEBHOOK_MANAGE_PERMISSION) },
          ),
    },
    { id: "openapi", label: t("developer.pane.openapi") },
  ];
}

/** The pane shown for `?pane=`: the requested pane when readable, else the first readable one. */
export function selectedPane(requested: DeveloperPane, tabs: readonly TabItem[]): DeveloperPane {
  const enabled = tabs.filter((tab) => tab.disabledReason === undefined).map((tab) => tab.id);
  if (enabled.includes(requested)) {
    return requested;
  }
  return developerPaneOf(enabled[0] ?? null);
}

function DeveloperPage() {
  const [params, setParams] = useSearchParams();
  const sandbox = sandboxTenantName(useShellSession()) !== null;
  const access = useAccess();
  const tabs = useMemo(() => developerTabs(access), [access]);
  const pane = selectedPane(developerPaneOf(params.get("pane")), tabs);
  const setPane = (next: string) => {
    setParams(
      (previous) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const nextParams = withPane(previous, next === "api-clients" ? null : next);
        return nextParams;
      },
      { replace: true },
    );
  };
  let panel: ReactNode;
  switch (pane) {
    case "api-clients":
      panel = <ApiClientsPane />;
      break;
    case "webhooks":
      panel = <WebhooksPane sandbox={sandbox} />;
      break;
    case "openapi":
      panel = <OpenApiPane />;
      break;
  }
  return (
    <div
      data-testid={PAGE_TEST_ID}
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={t("developer.title")} group="developer" />
      <PanelTabs label={t("developer.sections")} tabs={tabs} selectedId={pane} onChange={setPane}>
        <div className="flex min-h-0 flex-1 flex-col gap-4 pt-4">{panel}</div>
      </PanelTabs>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// One-time secret dialog (DS-CMP-11; REQ-PLT-033)
// ---------------------------------------------------------------------------------------------------

export interface RevealedSecret {
  readonly title: string;
  readonly testId: string;
  /** The client id row of an API client; a webhook endpoint has none. */
  readonly identifier: { readonly label: string; readonly value: string } | null;
  readonly secretLabel: string;
  readonly hiddenLabel: string;
  readonly secret: string;
}

/** The dialog of a created API client: null when the answer is a D-80 replay without the secret. */
export function clientSecretDialog(created: ApiClientSecret): RevealedSecret | null {
  if (created.client_secret === null) {
    return null;
  }
  return {
    title: t("developer.clients.secret.title", { name: created.name }),
    testId: "SF-16-dialog-client-secret",
    identifier: { label: t("developer.clients.secret.clientId"), value: created.client_id },
    secretLabel: t("developer.clients.secret.secret"),
    hiddenLabel: t("developer.clients.secret.hidden"),
    secret: created.client_secret,
  };
}

export function signingSecretDialog(created: WebhookEndpointCreated): RevealedSecret | null {
  if (created.signing_secret === null) {
    return null;
  }
  return {
    title: t("developer.webhooks.secret.title", { url: created.url }),
    testId: "SF-16-dialog-signing-secret",
    identifier: null,
    secretLabel: t("developer.webhooks.secret.secret"),
    hiddenLabel: t("developer.webhooks.secret.hidden"),
    secret: created.signing_secret,
  };
}

interface SecretDialogProps {
  readonly revealed: RevealedSecret;
  readonly onDone: () => void;
}

/**
 * SCREENS_B §9.15 one-time dialog: the warning, the masked secret with "Show" (`aria-pressed`) and
 * "Copy", the required acknowledgement and "Done", which reports "Confirm that you stored the secret."
 * until the box is checked. There is no Cancel, and Esc does not close it before the acknowledgement.
 */
export function SecretDialog({ revealed, onDone }: SecretDialogProps) {
  const toast = useToast();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const warningId = useId();
  const reasonId = useId();
  const checkboxId = useId();
  const [shown, setShown] = useState(false);
  const [stored, setStored] = useState(false);
  useModalFocus({ panel });

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (stored) {
          onDone();
        }
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => root.removeEventListener("keydown", onKeyDown);
  }, [stored, onDone]);

  const copy = async (label: string, value: string) => {
    if (typeof navigator.clipboard === "undefined") {
      return;
    }
    await navigator.clipboard.writeText(value);
    toast.show({ tone: "positive", message: t("developer.copied", { label }) });
  };
  const doneReason = t("developer.clients.secret.confirmStored");

  return createPortal(
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={warningId}
        tabIndex={-1}
        data-testid={revealed.testId}
        className="flex max-h-full w-[var(--modal-w-md)] max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <div className="flex flex-col gap-1 px-5 pt-5">
          <h2 id={titleId} className="text-title-md text-fg-1">
            {revealed.title}
          </h2>
          <p id={warningId} className="text-body-sm font-medium text-warning-fg">
            {t("developer.clients.secret.warning")}
          </p>
        </div>
        <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-5 pt-4">
          <dl className="flex flex-col gap-3 text-body-sm">
            {revealed.identifier === null ? null : (
              <div className="flex flex-wrap items-center gap-2">
                <dt className="w-28 shrink-0 text-fg-2">{revealed.identifier.label}</dt>
                <dd className="min-w-0 flex-1 break-all font-mono text-mono text-fg-1">
                  {revealed.identifier.value}
                </dd>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    void copy(revealed.identifier?.label ?? "", revealed.identifier?.value ?? "")
                  }
                >
                  {t("developer.copy")}
                </Button>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <dt className="w-28 shrink-0 text-fg-2">{revealed.secretLabel}</dt>
              <dd className="min-w-0 flex-1 break-all rounded-md bg-surface px-2 py-1 font-mono text-mono text-fg-1">
                {shown ? (
                  revealed.secret
                ) : (
                  <>
                    <span aria-hidden="true">{maskSecret(revealed.secret)}</span>
                    <span className="sr-only">{revealed.hiddenLabel}</span>
                  </>
                )}
              </dd>
              <Button
                variant="secondary"
                size="sm"
                aria-pressed={shown}
                onClick={() => {
                  setShown((previous) => !previous);
                }}
              >
                {t("developer.clients.secret.show")}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void copy(revealed.secretLabel, revealed.secret)}
              >
                {t("developer.copy")}
              </Button>
            </div>
          </dl>
          <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              required
              aria-required="true"
              checked={stored}
              onChange={(event) => {
                setStored(event.target.checked);
              }}
              className="size-4"
            />
            {t("developer.clients.secret.stored")}
          </label>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-3 px-5 py-4">
          {stored ? null : (
            <p id={reasonId} className="text-body-sm text-fg-2">
              {doneReason}
            </p>
          )}
          <Button
            variant="primary"
            aria-describedby={stored ? undefined : reasonId}
            disabledReason={stored ? undefined : doneReason}
            onClick={onDone}
          >
            {t("developer.clients.secret.done")}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------------------------------
// API clients
// ---------------------------------------------------------------------------------------------------

function clientStatusLabel(status: ApiClient["status"]): string {
  return chipFor("E-103", status)?.status ?? status;
}

/** SCREENS_B §9.15 API clients columns (RPT-27) with "Rotate secret" and "Revoke" on active clients. */
// API-C-09 sort keys: GET /api/v1/api-clients
export function clientColumns(
  onRotate: (client: ApiClient) => void,
  onRevoke: (client: ApiClient) => void,
): readonly GridColumn<ApiClient>[] {
  return [
    {
      id: "name",
      header: t("developer.clients.column.name"),
      kind: "identifier",
      value: (client) => client.name,
      sortKey: "name",
      width: 176,
    },
    {
      id: "client_id",
      header: t("developer.clients.column.clientId"),
      kind: "text",
      value: (client) => client.client_id,
      render: (client) => (
        <span className="font-mono text-mono text-fg-2" title={client.client_id}>
          {shortClientId(client.client_id)}
        </span>
      ),
      width: 200,
    },
    {
      id: "status",
      header: t("developer.clients.column.status"),
      kind: "status",
      value: (client) => client.status,
      render: (client) => <StatusChip status={clientStatusLabel(client.status)} />,
      width: 112,
    },
    {
      id: "scopes",
      header: t("developer.clients.column.scopes"),
      kind: "text",
      value: (client) => client.scopes.join(", "),
      width: 260,
    },
    {
      id: "entity_scope",
      header: t("developer.clients.column.entityScope"),
      kind: "text",
      value: (client) =>
        client.is_all_entities
          ? t("developer.clients.allEntities")
          : count("developer.clients.entityCount", client.entity_ids.length),
      width: 128,
    },
    {
      id: "rate_limit_per_minute",
      header: t("developer.clients.column.rateLimit"),
      kind: "number",
      numberKind: "count",
      value: (client) => String(client.rate_limit_per_minute),
      width: 144,
    },
    {
      id: "expires_at",
      header: t("developer.clients.column.expires"),
      kind: "timestamp",
      value: (client) => client.expires_at,
    },
    {
      id: "last_used_at",
      header: t("developer.clients.column.lastUsed"),
      kind: "timestamp",
      value: (client) => client.last_used_at,
    },
    {
      id: "secret_rotated_at",
      header: t("developer.clients.column.secretRotated"),
      kind: "timestamp",
      value: (client) => client.secret_rotated_at,
    },
    {
      id: "actions",
      header: t("developer.clients.column.actions"),
      kind: "actions",
      value: () => null,
      render: (client) =>
        client.status === "ACTIVE" ? (
          <span className="flex items-center gap-3">
            <Button
              variant="link"
              size="sm"
              onClick={() => {
                onRotate(client);
              }}
            >
              {t("developer.clients.rotate")}
            </Button>
            <Button
              variant="link"
              size="sm"
              onClick={() => {
                onRevoke(client);
              }}
            >
              {t("developer.clients.revoke")}
            </Button>
          </span>
        ) : null,
      width: 200,
    },
  ];
}

function ApiClientsPane() {
  const [creating, setCreating] = useState(false);
  const [rotating, setRotating] = useState<ApiClient | null>(null);
  const [revoking, setRevoking] = useState<ApiClient | null>(null);
  const [revealed, setRevealed] = useState<RevealedSecret | null>(null);
  const columns = useMemo(() => clientColumns(setRotating, setRevoking), []);
  const source: GridSource<ApiClient> = {
    queryKey: apiClientsGridKey(),
    fetchPage: fetchApiClientsPage,
  };
  const newClient = {
    label: t("developer.clients.new"),
    onAction: () => {
      setCreating(true);
    },
  };
  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<ApiClient>
          name="api-clients"
          title={t("developer.clients.grid")}
          errorTitle={t("developer.clients.loadError")}
          countLabel={(value, formatted) =>
            t("developer.clients.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(client) => client.id}
          rowLabel={(client) => client.name}
          testIdPrefix="SF-16"
          rowTestKey={(client) => clientTestKey(client.name)}
          toolbarActions={
            <Button variant="primary" onClick={newClient.onAction}>
              {newClient.label}
            </Button>
          }
          emptyState={
            <div data-testid="SF-16-empty-api-clients">
              <EmptyState
                title={t("developer.clients.empty.title")}
                description={t("developer.clients.empty.description")}
                action={newClient}
              />
            </div>
          }
        />
      </div>
      {creating ? (
        <NewApiClientDrawer
          entityChoice={ENTITY_CHOICE_AVAILABLE}
          onClose={() => {
            setCreating(false);
          }}
          onCreated={(secret) => {
            setCreating(false);
            setRevealed(secret);
          }}
        />
      ) : null}
      {rotating === null ? null : (
        <RotateSecretDialog
          client={rotating}
          onClose={() => {
            setRotating(null);
          }}
          onRotated={(secret) => {
            setRotating(null);
            setRevealed(secret);
          }}
        />
      )}
      {revoking === null ? null : (
        <RevokeClientDialog
          client={revoking}
          onClose={() => {
            setRevoking(null);
          }}
        />
      )}
      {revealed === null ? null : (
        <SecretDialog
          revealed={revealed}
          onDone={() => {
            setRevealed(null);
          }}
        />
      )}
    </>
  );
}

export interface ClientDraft {
  readonly name: string;
  readonly scopes: readonly string[];
  readonly allEntities: boolean;
  readonly entityCodes: readonly string[];
  /** The business date of the expiry, null while the typed text is empty or invalid. */
  readonly expires: string | null;
  readonly rateLimit: string;
}

export interface ClientDraftErrors {
  readonly name: string | null;
  readonly scopes: string | null;
  readonly entities: string | null;
  readonly expires: string | null;
  readonly rateLimit: string | null;
}

export function clientDraftErrors(draft: ClientDraft): ClientDraftErrors {
  return {
    name: draft.name.trim() === "" ? t("developer.clients.drawer.nameRequired") : null,
    scopes: draft.scopes.length === 0 ? t("developer.clients.drawer.scopesRequired") : null,
    entities:
      !draft.allEntities && draft.entityCodes.length === 0
        ? t("developer.clients.drawer.entitiesRequired")
        : null,
    expires: draft.expires === null ? t("developer.clients.drawer.expiresRequired") : null,
    rateLimit: RATE_LIMIT_PATTERN.test(draft.rateLimit.trim())
      ? null
      : t("developer.clients.drawer.rateLimitRequired"),
  };
}

export function clientDraftValid(errors: ClientDraftErrors): boolean {
  return Object.values(errors).every((error) => error === null);
}

/** The API-S-ApiClientIn body of a valid draft. */
export function clientInput(draft: ClientDraft): ApiClientCreate {
  return {
    name: draft.name.trim(),
    scopes: [...draft.scopes],
    is_all_entities: draft.allEntities,
    ...(draft.allEntities ? {} : { entity_codes: [...draft.entityCodes] }),
    expires_at: expiryInstant(draft.expires ?? ""),
    rate_limit_per_minute: Number(draft.rateLimit.trim()),
  };
}

/**
 * SCREENS_B §9.15 (rev 1.62): `POST /api-clients` refuses every entity code until the API admits an
 * entity scope on an API client (item API-CLIENT-ENTITY-SCOPE-1), so the drawer does not offer the
 * choice of entities. The choice returns when this is true.
 */
const ENTITY_CHOICE_AVAILABLE = false;

/** The API-S-ApiClientIn members each field of the drawer sends. */
const CLIENT_MEMBERS: Readonly<Record<keyof ClientDraftErrors, readonly string[]>> = {
  name: ["name"],
  scopes: ["scopes"],
  entities: ["entity_codes", "is_all_entities"],
  expires: ["expires_at"],
  rateLimit: ["rate_limit_per_minute"],
};

export interface NewApiClientDrawerProps {
  /** Whether "Selected entities" can be chosen; else it is shown unavailable with its reason. */
  readonly entityChoice: boolean;
  readonly onClose: () => void;
  readonly onCreated: (secret: RevealedSecret | null) => void;
}

/** SCREENS_B §9.15 "New API client": non-approval scopes only, step-up, then the one-time dialog. */
export function NewApiClientDrawer({ entityChoice, onClose, onCreated }: NewApiClientDrawerProps) {
  const formId = useId();
  const scopesHelpId = useId();
  const scopesErrorId = useId();
  const scopeLegendId = useId();
  const entityScopeErrorId = useId();
  const entityChoiceReasonId = useId();
  const toast = useToast();
  const permissions = usePermissions();
  const entities = useAllEntities();
  const groups = useMemo(() => scopeGroups(permissions.data ?? []), [permissions.data]);
  const [initialExpiry] = useState(() => defaultExpiry(Date.now()));
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<readonly string[]>([]);
  const [allEntities, setAllEntities] = useState(true);
  const [entityCodes, setEntityCodes] = useState<readonly string[]>([]);
  const [expiresText, setExpiresText] = useState(() => formatDate(initialExpiry));
  const [expires, setExpires] = useState<string | null>(initialExpiry);
  const [rateLimit, setRateLimit] = useState(String(DEFAULT_RATE_LIMIT));
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const create = useCommand<ApiClientSecret>({
    method: "POST",
    path: API_CLIENTS_PATH,
    invalidates: [EVERY_API_CLIENT],
  });
  const refusals = useFieldRefusals(create.problem, CLIENT_MEMBERS);
  const draft: ClientDraft = { name, scopes, allEntities, entityCodes, expires, rateLimit };
  const checked = attempted
    ? clientDraftErrors(draft)
    : { name: null, scopes: null, entities: null, expires: null, rateLimit: null };
  // The screen's own check first, then what the server said of the value it was sent.
  const errors: ClientDraftErrors = {
    name: checked.name ?? refusals.fields.name,
    scopes: checked.scopes ?? refusals.fields.scopes,
    entities: checked.entities ?? refusals.fields.entities,
    expires: checked.expires ?? refusals.fields.expires,
    rateLimit: checked.rateLimit ?? refusals.fields.rateLimit,
  };
  const dirty = name !== "" || scopes.length > 0 || !allEntities;

  const send = async () => {
    const outcome = await create.submit(clientInput(draft));
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("developer.clients.created", { name: outcome.data.name }),
      });
      onCreated(clientSecretDialog(outcome.data));
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (create.pending || !clientDraftValid(clientDraftErrors(draft))) {
      return;
    }
    void send();
  };

  let banner: ReactNode = null;
  if (create.problem !== null && create.problem.slug === SCOPE_NOT_ALLOWED_SLUG) {
    banner = (
      <Banner
        tone="negative"
        title={t("developer.clients.drawer.scopeNotAllowed")}
        announce="live"
      />
    );
  } else if (create.problem !== null && create.problem.slug !== STEP_UP_REQUIRED_SLUG) {
    banner = <RefusalBanner problem={refusals.banner} placed={refusals.placed} />;
  }

  const toggleScope = (code: string, on: boolean) => {
    refusals.edited("scopes");
    setScopes((previous) =>
      on
        ? [...previous.filter((item) => item !== code), code]
        : previous.filter((item) => item !== code),
    );
  };
  const entityOptions = (entities.data ?? []).map((entity) => ({
    value: entity.code,
    label: `${entity.code} · ${entity.name}`,
  }));
  // The refusal of the entities stands at "Entities" while that field is shown, else at the scope.
  const scopeRefusal = allEntities ? errors.entities : null;

  return (
    <>
      <Drawer
        open
        title={t("developer.clients.drawer.title")}
        dirty={dirty}
        submitting={create.pending}
        banner={banner}
        primaryAction={{ label: t("developer.clients.drawer.create"), form: formId }}
        onClose={onClose}
      >
        <form
          id={formId}
          noValidate
          data-testid="SF-16-drawer-api-client"
          onSubmit={submit}
          className="flex flex-col gap-4"
        >
          <Field
            name="api_client_name"
            label={t("developer.clients.drawer.name")}
            required
            error={errors.name}
          >
            {(control) => (
              <input
                {...control}
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={name}
                onChange={(event) => {
                  refusals.edited("name");
                  setName(event.target.value);
                }}
                className={controlClass(errors.name !== null)}
              />
            )}
          </Field>
          <fieldset
            aria-labelledby={scopeLegendId}
            aria-describedby={
              errors.scopes === null ? scopesHelpId : `${scopesErrorId} ${scopesHelpId}`
            }
            aria-required="true"
            className="flex flex-col gap-2"
          >
            <legend id={scopeLegendId} className="text-body-sm font-medium text-fg-1">
              {t("developer.clients.drawer.scopes")}
            </legend>
            {errors.scopes === null ? null : (
              <p id={scopesErrorId} className="text-body-sm text-negative-fg">
                {errors.scopes}
              </p>
            )}
            <p id={scopesHelpId} className="text-body-sm text-fg-3">
              {t("developer.clients.drawer.scopesHelp")}
            </p>
            {permissions.data === undefined ? (
              <Skeleton region={t("developer.clients.drawer.scopes")} shape="rows" count={4} />
            ) : (
              groups.map((group) => (
                <div
                  key={group.area}
                  role="group"
                  aria-label={group.area}
                  className="flex flex-col gap-1"
                >
                  <p className="text-caption font-medium uppercase text-fg-3">{group.area}</p>
                  {group.permissions.map((permission) => (
                    <label
                      key={permission.code}
                      className="flex items-start gap-2 text-body-sm text-fg-1"
                    >
                      <input
                        type="checkbox"
                        checked={scopes.includes(permission.code)}
                        onChange={(event) => {
                          toggleScope(permission.code, event.target.checked);
                        }}
                        className="mt-0.5 size-4 shrink-0"
                      />
                      <span>
                        <span className="font-mono text-mono">{permission.code}</span>{" "}
                        <span className="text-fg-2">{permission.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              ))
            )}
          </fieldset>
          <fieldset
            aria-describedby={scopeRefusal === null ? undefined : entityScopeErrorId}
            className="flex flex-col gap-2"
          >
            <legend className="text-body-sm font-medium text-fg-1">
              {t("developer.clients.drawer.entityScope")}
            </legend>
            {/* With no entity to choose, a refusal of the entities stands at the scope itself. */}
            {scopeRefusal === null ? null : (
              <p id={entityScopeErrorId} className="text-body-sm text-negative-fg">
                {scopeRefusal}
              </p>
            )}
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-body-sm text-fg-1">
                <input
                  type="radio"
                  name="api_client_entity_scope"
                  checked={allEntities}
                  onChange={() => {
                    refusals.edited("entities");
                    setAllEntities(true);
                    setEntityCodes([]);
                  }}
                />
                {t("developer.clients.drawer.entityScopeAll")}
              </label>
              <label
                className={cn(
                  "flex items-center gap-2 text-body-sm",
                  entityChoice ? "text-fg-1" : "text-fg-disabled",
                )}
              >
                <input
                  type="radio"
                  name="api_client_entity_scope"
                  checked={!allEntities}
                  // Unavailable, not disabled: the option keeps focus so that its reason is read. A
                  // click changes nothing: the choice is controlled, and the state does not move.
                  aria-disabled={entityChoice ? undefined : true}
                  aria-describedby={entityChoice ? undefined : entityChoiceReasonId}
                  onChange={() => {
                    if (entityChoice) {
                      refusals.edited("entities");
                      setAllEntities(false);
                    }
                  }}
                />
                {t("developer.clients.drawer.entityScopeSelected")}
              </label>
            </div>
            {entityChoice ? null : (
              <p id={entityChoiceReasonId} className="text-body-sm text-fg-3">
                {t("developer.clients.drawer.entityScopeAllOnly")}
              </p>
            )}
          </fieldset>
          {allEntities ? null : (
            <Field
              name="api_client_entities"
              label={t("developer.clients.drawer.entities")}
              required
              error={errors.entities}
            >
              {(control) => (
                <MultiSelect
                  control={control}
                  options={entityOptions}
                  values={entityCodes}
                  invalid={errors.entities !== null}
                  onChange={(codes) => {
                    refusals.edited("entities");
                    setEntityCodes(codes);
                  }}
                />
              )}
            </Field>
          )}
          <Field
            name="api_client_expires"
            label={t("developer.clients.drawer.expires")}
            required
            help={t("developer.clients.drawer.expiresHelp")}
            error={errors.expires}
            width="date"
          >
            {(control) => (
              <DateInput
                control={control}
                value={expiresText}
                onChange={(text) => {
                  refusals.edited("expires");
                  setExpiresText(text);
                }}
                onValue={setExpires}
                invalid={errors.expires !== null}
              />
            )}
          </Field>
          <Field
            name="api_client_rate_limit"
            label={t("developer.clients.drawer.rateLimit")}
            required
            error={errors.rateLimit}
            width="date"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                inputMode="numeric"
                autoComplete="off"
                value={rateLimit}
                onChange={(event) => {
                  refusals.edited("rateLimit");
                  setRateLimit(event.target.value);
                }}
                className={controlClass(errors.rateLimit !== null)}
              />
            )}
          </Field>
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

interface RotateSecretDialogProps {
  readonly client: ApiClient;
  readonly onClose: () => void;
  readonly onRotated: (secret: RevealedSecret | null) => void;
}

/** SCREENS_B §9.15 "Rotate secret": the confirmation, step-up when asked, then the one-time dialog. */
function RotateSecretDialog({ client, onClose, onRotated }: RotateSecretDialogProps) {
  const toast = useToast();
  const [stepUp, setStepUp] = useState(false);
  const rotate = useCommand<ApiClientSecret>({
    method: "POST",
    path: apiClientCommandPath(client.id, "rotate-secret"),
    invalidates: [EVERY_API_CLIENT],
  });
  const params = { name: client.name };
  const send = async () => {
    const outcome = await rotate.submit();
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({ tone: "positive", message: t("developer.clients.rotated", params) });
      onRotated(clientSecretDialog(outcome.data));
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
      return;
    }
    if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.detail ?? outcome.problem.title });
      onClose();
    }
  };
  return (
    <>
      <Modal
        open={!stepUp}
        variant="confirmation"
        title={t("developer.clients.rotateDialog.title", params)}
        description={t("developer.clients.rotateDialog.description")}
        primaryAction={{
          label: t("developer.clients.rotateDialog.confirm"),
          onAction: () => {
            void send();
          },
        }}
        submitting={rotate.pending}
        onClose={onClose}
        testId="SF-16-dialog-rotate-secret"
      />
      {stepUp ? (
        <StepUpModal
          onCancel={onClose}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

interface RevokeClientDialogProps {
  readonly client: ApiClient;
  readonly onClose: () => void;
}

/** The API-S-ApiClientRevokeIn member the dialog's one field sends. */
const REVOKE_MEMBERS: Readonly<Record<"reason", readonly string[]>> = { reason: ["reason"] };

/** SCREENS_B §9.15 "Revoke" (SB-R-05): the consequence, a reason and the Danger action. */
function RevokeClientDialog({ client, onClose }: RevokeClientDialogProps) {
  const formId = useId();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const revoke = useCommand<ApiClient>({
    method: "POST",
    path: apiClientCommandPath(client.id, "revoke"),
    invalidates: [EVERY_API_CLIENT],
  });
  const refusals = useFieldRefusals(revoke.problem, REVOKE_MEMBERS);
  const params = { name: client.name };
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await revoke.submit({ reason: reason.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("developer.clients.revoked", params) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("developer.clients.revokeDialog.title", params)}
      description={t("developer.clients.revokeDialog.description", params)}
      primaryAction={{
        label: t("developer.clients.revokeDialog.confirm"),
        destructive: true,
        form: formId,
      }}
      submitting={revoke.pending}
      onClose={onClose}
      testId="SF-16-dialog-revoke-api-client"
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
        <RefusalBanner problem={refusals.banner} placed={refusals.placed} />
        <ReasonField
          label={t("access.user.reason")}
          value={reason}
          onChange={(text) => {
            refusals.edited("reason");
            setReason(text);
          }}
          showError={attempted}
          error={refusals.fields.reason}
        />
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------------------------------
// Webhooks
// ---------------------------------------------------------------------------------------------------

function deliveryStatusLabel(status: WebhookDeliveryStatus): string {
  return chipFor("E-97", status)?.status ?? status;
}

/** SCREENS_B §9.15 endpoint columns; the actions column toggles `is_active` (SB-R-08 in a sandbox). */
// API-C-09 sort keys: GET /api/v1/webhook-endpoints
export function endpointColumns(sandbox: boolean): readonly GridColumn<WebhookEndpoint>[] {
  return [
    {
      id: "url",
      header: t("developer.webhooks.column.url"),
      kind: "identifier",
      value: (endpoint) => endpoint.url,
      render: (endpoint) => mono(endpoint.url),
      sortKey: "url",
      width: 280,
    },
    {
      id: "description",
      header: t("developer.webhooks.column.description"),
      kind: "text",
      value: (endpoint) => endpoint.description,
      width: 220,
    },
    {
      id: "event_kinds",
      header: t("developer.webhooks.column.events"),
      kind: "text",
      value: (endpoint) => endpoint.event_kinds.join(", "),
      render: (endpoint) => mono(endpoint.event_kinds.join(", ")),
      width: 280,
    },
    {
      id: "is_active",
      header: t("developer.webhooks.column.active"),
      kind: "boolean",
      value: (endpoint) => String(endpoint.is_active),
      width: 88,
    },
    {
      id: "created_at",
      header: t("developer.webhooks.column.created"),
      kind: "timestamp",
      value: (endpoint) => endpoint.created_at,
      sortKey: "created_at",
    },
    {
      id: "actions",
      header: t("developer.webhooks.column.actions"),
      kind: "actions",
      value: () => null,
      render: (endpoint) => <ActiveToggle endpoint={endpoint} sandbox={sandbox} />,
      width: 120,
    },
  ];
}

function ActiveToggle({
  endpoint,
  sandbox,
}: {
  readonly endpoint: WebhookEndpoint;
  readonly sandbox: boolean;
}) {
  const toast = useToast();
  const update = useCommand<WebhookEndpoint>({
    method: "PATCH",
    path: endpointPath(endpoint.id),
    invalidates: [EVERY_WEBHOOK],
  });
  const activating = !endpoint.is_active;
  const toggle = async () => {
    const outcome = await update.submit(
      { is_active: activating },
      { ifMatch: rowIfMatch(endpoint.row_version) },
    );
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t(activating ? "developer.webhooks.activated" : "developer.webhooks.deactivated", {
          url: endpoint.url,
        }),
      });
    } else if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.detail ?? outcome.problem.title });
    }
  };
  return (
    <Button
      variant="link"
      size="sm"
      loading={update.pending}
      disabledReason={activating && sandbox ? t("journals.sandboxReason") : undefined}
      onClick={() => void toggle()}
    >
      {t(activating ? "developer.webhooks.activate" : "developer.webhooks.deactivate")}
    </Button>
  );
}

/** SCREENS_B §9.15 deliveries columns; "Endpoint" shows the URL prefix of the delivery's endpoint. */
// API-C-09 sort keys: GET /api/v1/webhook-deliveries
export function deliveryColumns(
  endpoints: readonly WebhookEndpoint[],
): readonly GridColumn<WebhookDelivery>[] {
  const urls = new Map(endpoints.map((endpoint) => [endpoint.id, endpoint.url]));
  const endpointOf = (delivery: WebhookDelivery): string | null => {
    const url = urls.get(delivery.webhook_endpoint_id);
    return url === undefined ? null : urlPrefix(url);
  };
  return [
    {
      id: "endpoint",
      header: t("developer.deliveries.column.endpoint"),
      kind: "identifier",
      value: endpointOf,
      render: (delivery) => {
        const prefix = endpointOf(delivery);
        return prefix === null ? noValue() : mono(prefix);
      },
      width: 220,
    },
    {
      id: "event_kind",
      header: t("developer.deliveries.column.event"),
      kind: "text",
      value: (delivery) => delivery.event_kind,
      render: (delivery) => mono(delivery.event_kind),
      width: 200,
    },
    {
      id: "status",
      header: t("developer.deliveries.column.status"),
      kind: "status",
      value: (delivery) => delivery.status,
      render: (delivery) => <StatusChip status={deliveryStatusLabel(delivery.status)} />,
      width: 120,
    },
    {
      id: "attempt_count",
      header: t("developer.deliveries.column.attempts"),
      kind: "number",
      numberKind: "count",
      value: (delivery) => String(delivery.attempt_count),
      width: 96,
    },
    {
      id: "next_attempt_at",
      header: t("developer.deliveries.column.nextAttempt"),
      kind: "timestamp",
      value: (delivery) => delivery.next_attempt_at,
    },
    {
      id: "last_response_status",
      header: t("developer.deliveries.column.lastResponse"),
      kind: "text",
      value: (delivery) =>
        delivery.last_response_status === null ? null : String(delivery.last_response_status),
      render: (delivery) =>
        delivery.last_response_status === null ? (
          noValue()
        ) : (
          <span className="num">
            {formatNumber(delivery.last_response_status, { kind: "count" })}
          </span>
        ),
      width: 112,
    },
    {
      id: "last_error",
      header: t("developer.deliveries.column.lastError"),
      kind: "text",
      value: (delivery) => delivery.last_error,
      width: 260,
    },
    {
      id: "succeeded_at",
      header: t("developer.deliveries.column.succeeded"),
      kind: "timestamp",
      value: (delivery) => delivery.succeeded_at,
    },
  ];
}

/** SCREENS_B §9.15 `GET /webhook-deliveries?status`: the Status chip. */
export function deliveryFilterFields(): readonly FilterField[] {
  return [
    {
      name: "status",
      label: t("developer.deliveries.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: DELIVERY_STATUSES.map((status) => ({
        value: status,
        label: deliveryStatusLabel(status),
      })),
    },
  ];
}

export function deliveryStatusFilter(
  search: string,
  fields: readonly FilterField[],
): readonly string[] {
  return (
    parseFilters(search, fields).filters.find((filter) => filter.field === "status")?.values ?? []
  );
}

function WebhooksPane({ sandbox }: { readonly sandbox: boolean }) {
  const { search } = useLocation();
  const [creating, setCreating] = useState(false);
  const [revealed, setRevealed] = useState<RevealedSecret | null>(null);
  const [deliveryTotal, setDeliveryTotal] = useState<number | undefined>(undefined);
  const endpoints = useAllEndpoints();
  const fields = useMemo(() => deliveryFilterFields(), []);
  const status = deliveryStatusFilter(search, fields);
  const endpointCols = useMemo(() => endpointColumns(sandbox), [sandbox]);
  const deliveryCols = useMemo(() => deliveryColumns(endpoints.data ?? []), [endpoints.data]);
  const endpointSource: GridSource<WebhookEndpoint> = {
    queryKey: endpointsGridKey(),
    fetchPage: fetchEndpointsPage,
  };
  const deliverySource: GridSource<WebhookDelivery> = {
    queryKey: deliveriesGridKey(status),
    fetchPage: (cursor, sort) => fetchDeliveriesPage(status, cursor, sort),
  };
  const newEndpoint = {
    label: t("developer.webhooks.new"),
    onAction: () => {
      setCreating(true);
    },
  };
  // SB-R-08 (05 SBX-08): an endpoint is created active, so a sandbox creates none; the API
  // answers 403 `sandbox-restricted` to the command this control would send.
  const sandboxReason = sandbox ? t("journals.sandboxReason") : undefined;
  return (
    <>
      <section aria-label={t("developer.webhooks.grid")} className="flex flex-col gap-2">
        <div className="flex min-h-0 flex-col" style={{ minBlockSize: "16rem" }}>
          <DataGrid<WebhookEndpoint>
            name="webhooks"
            title={t("developer.webhooks.grid")}
            errorTitle={t("developer.webhooks.loadError")}
            countLabel={(value, formatted) =>
              t("developer.webhooks.count", { count: value, formatted })
            }
            columns={endpointCols}
            source={endpointSource}
            rowKey={(endpoint) => endpoint.id}
            rowLabel={(endpoint) => endpoint.url}
            testIdPrefix="SF-16"
            rowTestKey={(endpoint) => `endpoint-${endpoint.id}`}
            toolbarActions={
              <Button
                variant="primary"
                disabledReason={sandboxReason}
                onClick={newEndpoint.onAction}
              >
                {newEndpoint.label}
              </Button>
            }
            emptyState={
              <div data-testid="SF-16-empty-webhooks">
                <EmptyState
                  title={t("developer.webhooks.empty.title")}
                  description={t("developer.webhooks.empty.description")}
                  action={sandbox ? undefined : newEndpoint}
                />
              </div>
            }
          />
        </div>
      </section>
      <section
        aria-label={t("developer.deliveries.grid")}
        className="flex min-h-0 flex-1 flex-col gap-2"
      >
        <div className="flex min-h-0 flex-1 flex-col" style={{ minBlockSize: "16rem" }}>
          <DataGrid<WebhookDelivery>
            name="webhook-deliveries"
            title={t("developer.deliveries.grid")}
            errorTitle={t("developer.deliveries.loadError")}
            countLabel={(value, formatted) =>
              t("developer.deliveries.count", { count: value, formatted })
            }
            columns={deliveryCols}
            source={deliverySource}
            rowKey={(delivery) => delivery.id}
            rowLabel={(delivery) => delivery.event_kind}
            testIdPrefix="SF-16"
            rowTestKey={(delivery) => `delivery-${delivery.id}`}
            onTotalChange={(next) => setDeliveryTotal(next?.count)}
            filterBar={
              <FilterBar
                fields={fields}
                resultCount={deliveryTotal}
                resultLabel={(value) => count("developer.deliveries.count", value)}
                testId="SF-16-filter-bar-webhook-deliveries"
              />
            }
            emptyState={
              <EmptyState
                title={t("developer.deliveries.empty.title")}
                description={t("developer.deliveries.empty.description")}
              />
            }
            noResults={
              <EmptyState
                title={t("developer.deliveries.empty.title")}
                description={t("developer.deliveries.empty.description")}
              />
            }
          />
        </div>
      </section>
      {creating ? (
        <NewWebhookDrawer
          onClose={() => {
            setCreating(false);
          }}
          onCreated={(secret) => {
            setCreating(false);
            setRevealed(secret);
          }}
        />
      ) : null}
      {revealed === null ? null : (
        <SecretDialog
          revealed={revealed}
          onDone={() => {
            setRevealed(null);
          }}
        />
      )}
    </>
  );
}

export interface EndpointDraft {
  readonly url: string;
  readonly description: string;
  readonly events: readonly string[];
}

export interface EndpointDraftErrors {
  readonly url: string | null;
  readonly events: string | null;
}

export function endpointDraftErrors(draft: EndpointDraft): EndpointDraftErrors {
  return {
    url: acceptableWebhookUrl(draft.url) ? null : t("developer.webhooks.drawer.urlRule"),
    events: draft.events.length === 0 ? t("developer.webhooks.drawer.eventsRequired") : null,
  };
}

/** The API-S-WebhookEndpointIn body of a valid draft. */
export function endpointInput(draft: EndpointDraft): WebhookEndpointCreate {
  const description = draft.description.trim();
  return {
    url: draft.url.trim(),
    event_kinds: [...draft.events],
    ...(description === "" ? {} : { description }),
  };
}

interface NewWebhookDrawerProps {
  readonly onClose: () => void;
  readonly onCreated: (secret: RevealedSecret | null) => void;
}

/** The API-S-WebhookEndpointIn members each field of the drawer sends. */
const ENDPOINT_MEMBERS: Readonly<Record<"url" | "description" | "events", readonly string[]>> = {
  url: ["url"],
  description: ["description"],
  events: ["event_kinds"],
};

/** SCREENS_B §9.15 "New webhook endpoint": an https URL, a description and the events it receives. */
function NewWebhookDrawer({ onClose, onCreated }: NewWebhookDrawerProps) {
  const formId = useId();
  const eventsLegendId = useId();
  const eventsErrorId = useId();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [events, setEvents] = useState<readonly string[]>([]);
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<WebhookEndpointCreated>({
    method: "POST",
    path: WEBHOOK_ENDPOINTS_PATH,
    invalidates: [EVERY_WEBHOOK, EVERY_DELIVERY],
  });
  const refusals = useFieldRefusals(create.problem, ENDPOINT_MEMBERS);
  const draft: EndpointDraft = { url, description, events };
  const checked = attempted ? endpointDraftErrors(draft) : { url: null, events: null };
  // The screen's own check first, then what the server said of the value it was sent.
  const errors = {
    url: checked.url ?? refusals.fields.url,
    description: refusals.fields.description,
    events: checked.events ?? refusals.fields.events,
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    const current = endpointDraftErrors(draft);
    if (create.pending || current.url !== null || current.events !== null) {
      return;
    }
    const outcome = await create.submit(endpointInput(draft));
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("developer.webhooks.created", { url: outcome.data.url }),
      });
      onCreated(signingSecretDialog(outcome.data));
    }
  };
  return (
    <Drawer
      open
      title={t("developer.webhooks.drawer.title")}
      dirty={url !== "" || description !== "" || events.length > 0}
      submitting={create.pending}
      banner={<RefusalBanner problem={refusals.banner} placed={refusals.placed} />}
      primaryAction={{ label: t("developer.webhooks.drawer.create"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-16-drawer-webhook-endpoint"
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <Field
          name="webhook_url"
          label={t("developer.webhooks.drawer.url")}
          required
          help={t("developer.webhooks.drawer.urlRule")}
          error={errors.url}
        >
          {(control) => (
            <input
              {...control}
              type="url"
              autoComplete="off"
              spellCheck={false}
              value={url}
              onChange={(event) => {
                refusals.edited("url");
                setUrl(event.target.value);
              }}
              className={`${controlClass(errors.url !== null)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="webhook_description"
          label={t("developer.webhooks.drawer.description")}
          optional
          error={errors.description}
        >
          {(control) => (
            <input
              {...control}
              type="text"
              autoComplete="off"
              value={description}
              onChange={(event) => {
                refusals.edited("description");
                setDescription(event.target.value);
              }}
              className={controlClass(errors.description !== null)}
            />
          )}
        </Field>
        <fieldset
          aria-labelledby={eventsLegendId}
          aria-describedby={errors.events === null ? undefined : eventsErrorId}
          aria-required="true"
          className="flex flex-col gap-2"
        >
          <legend id={eventsLegendId} className="text-body-sm font-medium text-fg-1">
            {t("developer.webhooks.drawer.events")}
          </legend>
          {errors.events === null ? null : (
            <p id={eventsErrorId} className="text-body-sm text-negative-fg">
              {errors.events}
            </p>
          )}
          {WEBHOOK_EVENT_KINDS.map((kind) => (
            <label key={kind} className="flex items-center gap-2 text-body-sm text-fg-1">
              <input
                type="checkbox"
                checked={events.includes(kind)}
                onChange={(event) => {
                  refusals.edited("events");
                  setEvents((previous) =>
                    event.target.checked
                      ? [...previous.filter((item) => item !== kind), kind]
                      : previous.filter((item) => item !== kind),
                  );
                }}
                className="size-4"
              />
              <span className="font-mono text-mono">{kind}</span>
            </label>
          ))}
        </fieldset>
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------
// OpenAPI
// ---------------------------------------------------------------------------------------------------

/** SCREENS_B §9.15 OpenAPI tab: the base URL, the token endpoint, the rate limit and the document. */
export function openApiLines(origin: string): readonly string[] {
  return [
    t("developer.openapi.baseUrl", { url: `${origin}/api/v1` }),
    t("developer.openapi.token"),
    t("developer.openapi.rateLimit", {
      formatted: formatNumber(DEFAULT_RATE_LIMIT, { kind: "count" }),
      formattedDefault: formatNumber(DEFAULT_RATE_LIMIT, { kind: "count" }),
    }),
  ];
}

function OpenApiPane() {
  const lines = openApiLines(window.location.origin);
  return (
    <section
      aria-label={t("developer.pane.openapi")}
      data-testid="SF-16-pane-openapi"
      className="flex flex-col gap-3 text-body-sm text-fg-1"
    >
      <ul className="flex flex-col gap-2">
        {lines.map((line) => (
          <li key={line} className="num">
            {line}
          </li>
        ))}
      </ul>
      <p>
        <a
          href={OPENAPI_PATH}
          download="openapi.json"
          className="font-medium text-accent-fg hover:underline"
        >
          {t("developer.openapi.download")}
        </a>
      </p>
    </section>
  );
}
