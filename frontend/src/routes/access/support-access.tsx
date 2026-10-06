// SF-14:support-access Support access (SCREENS_B §9.14; SCREENS §0.4 RT-92, §0.3 SCR-IA-03, SB-R-05,
// §0.7 SCR-PERM-01, SCR-ST-03, §0.4 E-96; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-CMP-29;
// 04 API-R-14 `GET /support-grants?status`, `POST /support-grants/{id}/revoke`; T-PLT-33; REQ-PLT-036;
// SAR-29; NTF-12 landing; BUILD_SPEC WEB-22). The Settings frame with the Access route tabs, one info
// banner per pending request ("Support access requested by operator <name>: read-only from <start> to
// <end>." with "Review in Approvals"), and the DataGrid "Support grants" (operator, scope "Read-only",
// reason, ticket, valid from, valid to, E-96 chip, approval link, approved, revoked) with the Status
// filter and "Revoke" on approved, unexpired grants (a reason of at least 10 characters; "The operator's
// sessions end immediately."). The empty state reads "No support access". "View operator activity"
// binds the audit log and is added by the RPS item that builds it (BS1-D-14).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation } from "react-router";

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
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { accessOf, useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import { GRANT_STATUSES } from "../../lib/api/queries/roles";
import {
  EVERY_SUPPORT_GRANT,
  fetchPendingGrants,
  fetchSupportGrantsPage,
  type GrantStatus,
  isRevocable,
  pendingGrantsKey,
  SUPPORT_GRANT_APPROVE_PERMISSION,
  type SupportGrant,
  type SupportGrantQuery,
  supportGrantRevokePath,
  supportGrantsKey,
} from "../../lib/api/queries/support-grants";
import { formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader, useBuiltPaths } from "../settings/index";
import { APPROVAL_REQUEST_ROUTE } from "./user";

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

function grantLabel(status: GrantStatus): string {
  return chipFor("E-96", status)?.status ?? status;
}

function approvalRoute(requestId: string): string {
  return `/approvals/requests/${requestId}`;
}

/** SCREENS_B §9.14 grants grid columns; "Revoke" only for a holder of `support_grant.approve`. */
export function grantColumns(
  canRevoke: boolean,
  approvalsBuilt: boolean,
  nowMs: number,
  onRevoke: (grant: SupportGrant) => void,
): readonly GridColumn<SupportGrant>[] {
  const columns: GridColumn<SupportGrant>[] = [
    {
      id: "operator",
      header: t("access.supportAccess.column.operator"),
      kind: "identifier",
      value: (grant) => grant.operator.display_name,
      width: 200,
    },
    {
      id: "scope",
      header: t("access.supportAccess.column.scope"),
      kind: "text",
      value: () => t("access.supportAccess.scope.readOnly"),
      width: 112,
    },
    {
      id: "reason",
      header: t("access.supportAccess.column.reason"),
      kind: "text",
      value: (grant) => grant.reason,
      width: 320,
    },
    {
      id: "ticket_ref",
      header: t("access.supportAccess.column.ticket"),
      kind: "text",
      value: (grant) => grant.ticket_ref,
      render: (grant) =>
        grant.ticket_ref === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : (
          mono(grant.ticket_ref)
        ),
      width: 120,
    },
    {
      id: "valid_from",
      header: t("access.supportAccess.column.validFrom"),
      kind: "timestamp",
      value: (grant) => grant.valid_from,
      sortKey: "valid_from",
    },
    {
      id: "valid_to",
      header: t("access.supportAccess.column.validTo"),
      kind: "timestamp",
      value: (grant) => grant.valid_to,
      sortKey: "valid_to",
    },
    {
      id: "status",
      header: t("access.supportAccess.column.status"),
      kind: "status",
      value: (grant) => grant.status,
      render: (grant) => <StatusChip status={grantLabel(grant.status)} />,
    },
    {
      id: "approval",
      header: t("access.supportAccess.column.approval"),
      kind: "text",
      value: (grant) => grant.approval_request_id,
      render: (grant) =>
        grant.approval_request_id === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : approvalsBuilt ? (
          <Link
            to={approvalRoute(grant.approval_request_id)}
            className="text-accent-fg hover:underline"
          >
            {t("access.supportAccess.approvalLink")}
          </Link>
        ) : (
          <span>{t("access.supportAccess.approvalLink")}</span>
        ),
      width: 112,
    },
    {
      id: "approved_at",
      header: t("access.supportAccess.column.approved"),
      kind: "timestamp",
      value: (grant) => grant.approved_at,
    },
    {
      id: "revoked_at",
      header: t("access.supportAccess.column.revoked"),
      kind: "timestamp",
      value: (grant) => grant.revoked_at,
    },
  ];
  if (canRevoke) {
    columns.push({
      id: "actions",
      header: t("access.supportAccess.column.actions"),
      kind: "actions",
      value: () => null,
      render: (grant) =>
        isRevocable(grant, nowMs) ? (
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              onRevoke(grant);
            }}
          >
            {t("access.supportAccess.revoke")}
          </Button>
        ) : null,
      width: 120,
    });
  }
  return columns;
}

/** SCREENS_B §9.14 `GET /support-grants?status`: the Status chip. */
export function grantFilterFields(): readonly FilterField[] {
  return [
    {
      name: "status",
      label: t("access.supportAccess.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: GRANT_STATUSES.map((status) => ({ value: status, label: grantLabel(status) })),
    },
  ];
}

export function grantQuery(search: string, fields: readonly FilterField[]): SupportGrantQuery {
  const parsed = parseFilters(search, fields);
  return { status: parsed.filters.find((filter) => filter.field === "status")?.values ?? [] };
}

/** SCREENS_B §9.14 banner copy for one pending request. */
export function pendingRequestText(grant: SupportGrant): string {
  return t("access.supportAccess.pending", {
    operator: grant.operator.display_name,
    from: formatTimestamp(grant.valid_from),
    to: formatTimestamp(grant.valid_to),
  });
}

function PendingRequests({ approvalsBuilt }: { readonly approvalsBuilt: boolean }) {
  const pending = useQuery({ queryKey: pendingGrantsKey(), queryFn: fetchPendingGrants });
  const items = pending.data ?? [];
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-2">
      {items.map((grant) => (
        <div key={grant.id} data-testid="SF-14-banner-support-request">
          <Banner
            tone="info"
            title={pendingRequestText(grant)}
            actions={
              grant.approval_request_id !== null && approvalsBuilt ? (
                <Link
                  to={approvalRoute(grant.approval_request_id)}
                  className="text-body-sm font-medium text-accent-fg hover:underline"
                >
                  {t("access.supportAccess.reviewInApprovals")}
                </Link>
              ) : (
                <span className="text-body-sm text-fg-2">
                  {t("access.supportAccess.reviewInApprovals")}
                </span>
              )
            }
          />
        </div>
      ))}
    </div>
  );
}

export function SupportAccessScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.supportAccess.title");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsForAll(SUPPORT_GRANT_APPROVE_PERMISSION)) {
    // The grants of the workspace are listed to, and revoked by, a holder for all entities alone.
    body = (
      <AccessLimited
        area={title}
        permissions={[SUPPORT_GRANT_APPROVE_PERMISSION]}
        allEntities={
          access.holdsAnywhere(SUPPORT_GRANT_APPROVE_PERMISSION)
            ? {
                message: "access.supportAccess.access.allEntities",
                permission: SUPPORT_GRANT_APPROVE_PERMISSION,
              }
            : undefined
        }
      />
    );
  } else {
    return <SupportAccessPage me={me.data} />;
  }
  return (
    <div
      data-testid="SF-14-support-access-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

function SupportAccessPage({ me }: { readonly me: Me }) {
  const { search } = useLocation();
  const built = useBuiltPaths();
  const [revoking, setRevoking] = useState<SupportGrant | null>(null);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const title = t("access.supportAccess.title");
  const fields = useMemo(() => grantFilterFields(), []);
  const query = grantQuery(search, fields);
  const canRevoke = accessOf(me).holdsForAll(SUPPORT_GRANT_APPROVE_PERMISSION);
  const approvalsBuilt = built.has(APPROVAL_REQUEST_ROUTE);
  // The revocable window is judged once per render of the columns, not once per row paint.
  const nowMs = Date.now();
  const columns = useMemo(
    () => grantColumns(canRevoke, approvalsBuilt, nowMs, setRevoking),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- nowMs changes every render by design
    [canRevoke, approvalsBuilt],
  );
  const source: GridSource<SupportGrant> = {
    queryKey: supportGrantsKey(query),
    fetchPage: (cursor, sort) => fetchSupportGrantsPage(query, cursor, sort),
  };
  const countLabel = (value: number) =>
    t("access.supportAccess.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  return (
    <div
      data-testid="SF-14-support-access-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access">
        {total === undefined ? null : (
          <p className="num text-body-sm text-fg-3">{countLabel(total)}</p>
        )}
      </SettingsPageHeader>
      <PendingRequests approvalsBuilt={approvalsBuilt} />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<SupportGrant>
          name="support-grants"
          title={t("access.supportAccess.grid")}
          errorTitle={t("access.supportAccess.loadError")}
          countLabel={(value, formatted) =>
            t("access.supportAccess.count", { count: value, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(grant) => grant.id}
          rowLabel={(grant) => grant.operator.display_name}
          testIdPrefix="SF-14"
          rowTestKey={(grant) => grant.id}
          onTotalChange={(next) => setTotal(next?.count)}
          filterBar={
            <FilterBar
              fields={fields}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-14-filter-bar-support-grants"
            />
          }
          emptyState={
            <div data-testid="SF-14-empty-support-grants">
              <EmptyState
                title={t("access.supportAccess.empty.title")}
                description={t("access.supportAccess.empty.description")}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("access.supportAccess.noResults.title")}
              description={t("access.supportAccess.noResults.description")}
            />
          }
        />
      </div>
      {revoking === null ? null : (
        <RevokeGrantDialog
          grant={revoking}
          onClose={() => {
            setRevoking(null);
          }}
        />
      )}
    </div>
  );
}

/** SCREENS_B §9.14 "Revoke support access" (SB-R-05): the consequence, a reason and the Danger action. */
export function RevokeGrantDialog({
  grant,
  onClose,
}: {
  readonly grant: SupportGrant;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const revoke = useCommand<SupportGrant>({
    method: "POST",
    path: supportGrantRevokePath(grant.id),
    invalidates: [EVERY_SUPPORT_GRANT],
  });
  const params = { operator: grant.operator.display_name };
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await revoke.submit({ reason: reason.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("access.supportAccess.revoked", params) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("access.supportAccess.revokeDialog.title", params)}
      description={t("access.supportAccess.revokeDialog.description")}
      primaryAction={{
        label: t("access.supportAccess.revokeDialog.confirm"),
        destructive: true,
        form: formId,
      }}
      submitting={revoke.pending}
      onClose={onClose}
      testId="SF-14-dialog-revoke-support-grant"
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
