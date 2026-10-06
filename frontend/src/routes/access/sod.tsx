// SF-14:sod Separation of duties (SCREENS_B §9.12; SCREENS §0.4 RT-89, §0.3 SB-R-05, §0.7 SCR-PERM-01,
// SCR-ST-03, §0.8 E-12, §0.4 E-96; DESIGN_SYSTEM DS-CMP-07, DS-CMP-10, DS-CMP-11, DS-CMP-19; 04 API-R-07
// `GET /sod-rules`, `GET /sod-exceptions?status`, `POST /sod-exceptions/{id}/revoke`; T-PLT-13, T-PLT-14;
// REQ-PLT-010, REQ-PLT-011; BS1-D-14; BUILD_SPEC WEB-20). The Settings frame with the Access route tabs
// and the panel tabs "Rules" and "Exceptions" (`pane=rules|exceptions`; the default omits `pane`). Rules:
// the DataGrid "SoD rules" with code, name, function A and B permissions, rationale, version and the
// E-12 chip. Exceptions: the DataGrid "SoD exceptions" with member, rule, compensating control, validity,
// the E-96 chip, the approval link and "Revoke exception" (`role.manage`, a reason of at least 10
// characters, the SB-R-05 consequence). The "SoD conflict report" link is not rendered (BS1-D-14), and
// proposing a rule version (`POST /sod-rules/{code}/versions`) has no interaction copy in §9.12, so no
// control renders for it (lane record F-ADM).
import { type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { accessOf, useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  EVERY_SOD_EXCEPTION,
  fetchSodExceptionsPage,
  fetchSodRulesPage,
  GRANT_STATUSES,
  type GrantStatus,
  REVOCABLE_EXCEPTION_STATUSES,
  type SodException,
  sodExceptionRevokePath,
  type SodExceptionQuery,
  sodExceptionsKey,
  type SodRule,
  sodRulesListKey,
} from "../../lib/api/queries/roles";
import { ROLE_MANAGE_PERMISSION } from "../../lib/api/queries/users";
import { formatNumber, NO_VALUE, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader, useBuiltPaths } from "../settings/index";
import { APPROVAL_REQUEST_ROUTE } from "./user";

export type SodPane = "rules" | "exceptions";

/** SCREENS_B §9.12 `pane=rules|exceptions`; anything else is the Rules pane. */
export function sodPaneOf(value: string | null): SodPane {
  return value === "exceptions" ? "exceptions" : "rules";
}

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

function grantLabel(status: GrantStatus): string {
  return chipFor("E-96", status)?.status ?? status;
}

/** SCREENS_B §9.12 rules grid columns. */
// API-C-09 sort keys: GET /api/v1/sod-rules
export function ruleColumns(): readonly GridColumn<SodRule>[] {
  return [
    {
      id: "code",
      header: t("access.sod.rules.column.rule"),
      kind: "identifier",
      value: (rule) => rule.code,
      render: (rule) => mono(rule.code),
      sortKey: "code",
      width: 104,
    },
    {
      id: "name",
      header: t("access.sod.rules.column.name"),
      kind: "text",
      value: (rule) => rule.name,
      width: 320,
    },
    {
      id: "function_a",
      header: t("access.sod.rules.column.functionA"),
      kind: "text",
      value: (rule) => rule.function_a_permissions.join(", "),
      render: (rule) => mono(rule.function_a_permissions.join(", ")),
      width: 240,
    },
    {
      id: "function_b",
      header: t("access.sod.rules.column.functionB"),
      kind: "text",
      value: (rule) => rule.function_b_permissions.join(", "),
      render: (rule) => mono(rule.function_b_permissions.join(", ")),
      width: 240,
    },
    {
      id: "rationale",
      header: t("access.sod.rules.column.rationale"),
      kind: "text",
      value: (rule) => rule.rationale,
      width: 320,
    },
    {
      id: "version",
      header: t("access.sod.rules.column.version"),
      kind: "text",
      value: (rule) =>
        t("access.sod.rules.version", {
          version: formatNumber(rule.version_no, { kind: "count" }),
        }),
      width: 96,
    },
    {
      id: "status",
      header: t("access.sod.rules.column.status"),
      kind: "status",
      value: (rule) => rule.status,
      render: (rule) => {
        const chip = chipFor("E-12", rule.status);
        return chip === null ? null : <StatusChip status={chip.status} />;
      },
    },
  ];
}

/** SCREENS_B §9.12 exceptions grid columns. */
export function exceptionColumns(
  canRevoke: boolean,
  approvalsBuilt: boolean,
  onRevoke: (exception: SodException) => void,
): readonly GridColumn<SodException>[] {
  const columns: GridColumn<SodException>[] = [
    {
      id: "member_name",
      header: t("access.sod.exceptions.column.user"),
      kind: "identifier",
      value: (exception) => exception.member_name,
      width: 200,
    },
    {
      id: "sod_rule_code",
      header: t("access.sod.exceptions.column.rule"),
      kind: "text",
      value: (exception) => exception.sod_rule_code,
      render: (exception) => mono(exception.sod_rule_code),
      width: 104,
    },
    {
      id: "compensating_control",
      header: t("access.sod.exceptions.column.control"),
      kind: "text",
      value: (exception) => exception.compensating_control,
      width: 360,
    },
    // 04 T-PLT-14 `valid_from` and `valid_to` are instants; SCREENS_B §9.12 shows DS-FMT-16 dates (UTC).
    {
      id: "valid_from",
      header: t("access.sod.exceptions.column.validFrom"),
      kind: "date",
      value: (exception) => timestampDate(exception.valid_from),
    },
    {
      id: "valid_to",
      header: t("access.sod.exceptions.column.validTo"),
      kind: "date",
      value: (exception) => timestampDate(exception.valid_to),
    },
    {
      id: "status",
      header: t("access.sod.exceptions.column.status"),
      kind: "status",
      value: (exception) => exception.status,
      render: (exception) => <StatusChip status={grantLabel(exception.status)} />,
    },
    {
      id: "approval",
      header: t("access.sod.exceptions.column.approval"),
      kind: "text",
      value: (exception) => exception.approval_request_id,
      render: (exception) =>
        exception.approval_request_id === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : approvalsBuilt ? (
          <Link
            to={`/approvals/requests/${exception.approval_request_id}`}
            className="text-accent-fg hover:underline"
          >
            {t("access.sod.exceptions.approvalLink")}
          </Link>
        ) : (
          <span>{t("access.sod.exceptions.approvalLink")}</span>
        ),
      width: 112,
    },
  ];
  if (canRevoke) {
    columns.push({
      id: "actions",
      header: t("access.sod.exceptions.column.actions"),
      kind: "actions",
      value: () => null,
      render: (exception) =>
        REVOCABLE_EXCEPTION_STATUSES.has(exception.status) ? (
          <Button
            variant="link"
            size="sm"
            onClick={() => {
              onRevoke(exception);
            }}
          >
            {t("access.sod.exceptions.revoke")}
          </Button>
        ) : null,
      width: 160,
    });
  }
  return columns;
}

/** SCREENS_B §9.12 `GET /sod-exceptions?status`: the Status chip of the exceptions pane. */
export function exceptionFilterFields(): readonly FilterField[] {
  return [
    {
      name: "status",
      label: t("access.sod.exceptions.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: GRANT_STATUSES.map((status) => ({ value: status, label: grantLabel(status) })),
    },
  ];
}

export function exceptionQuery(search: string, fields: readonly FilterField[]): SodExceptionQuery {
  const parsed = parseFilters(search, fields);
  return { status: parsed.filters.find((filter) => filter.field === "status")?.values ?? [] };
}

export function SodScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("access.sod.title");
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
    return <SodPage me={me.data} />;
  }
  return (
    <div
      data-testid="SF-14-sod-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      {body}
    </div>
  );
}

function SodPage({ me }: { readonly me: Me }) {
  const [params, setParams] = useSearchParams();
  const pane = sodPaneOf(params.get("pane"));
  const setPane = (next: string) => {
    setParams(
      (current) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const copy = withPane(current, next === "rules" ? null : next);
        return copy;
      },
      { replace: true },
    );
  };
  const title = t("access.sod.title");
  return (
    <div
      data-testid="SF-14-sod-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="access" />
      <div className="flex min-h-0 flex-1 flex-col">
        <PanelTabs
          label={t("access.sod.panes.label")}
          tabs={[
            { id: "rules", label: t("access.sod.panes.rules") },
            { id: "exceptions", label: t("access.sod.panes.exceptions") },
          ]}
          selectedId={pane}
          onChange={setPane}
        >
          {pane === "rules" ? <RulesPane /> : <ExceptionsPane me={me} />}
        </PanelTabs>
      </div>
    </div>
  );
}

function RulesPane() {
  const columns = useMemo(() => ruleColumns(), []);
  const source: GridSource<SodRule> = { queryKey: sodRulesListKey(), fetchPage: fetchSodRulesPage };
  return (
    <div data-testid="SF-14-pane-rules" className="flex min-h-0 flex-1 flex-col pt-3">
      <DataGrid<SodRule>
        name="sod-rules"
        title={t("access.sod.rules.grid")}
        errorTitle={t("access.sod.rules.loadError")}
        countLabel={(value, formatted) => t("access.sod.rules.count", { count: value, formatted })}
        columns={columns}
        source={source}
        rowKey={(rule) => rule.id}
        rowLabel={(rule) => rule.code}
        testIdPrefix="SF-14"
        rowTestKey={(rule) => rule.code}
      />
    </div>
  );
}

function ExceptionsPane({ me }: { readonly me: Me }) {
  const { search } = useLocation();
  const built = useBuiltPaths();
  const [revoking, setRevoking] = useState<SodException | null>(null);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const fields = useMemo(() => exceptionFilterFields(), []);
  const query = exceptionQuery(search, fields);
  // An exception names no entity of its own; the API judges the revocation (SCR-PERM-05).
  const canRevoke = accessOf(me).holdsAnywhere(ROLE_MANAGE_PERMISSION);
  const approvalsBuilt = built.has(APPROVAL_REQUEST_ROUTE);
  const columns = useMemo(
    () => exceptionColumns(canRevoke, approvalsBuilt, setRevoking),
    [canRevoke, approvalsBuilt],
  );
  const source: GridSource<SodException> = {
    queryKey: sodExceptionsKey(query),
    fetchPage: (cursor, sort) => fetchSodExceptionsPage(query, cursor, sort),
  };
  const countLabel = (value: number) =>
    t("access.sod.exceptions.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  return (
    <div data-testid="SF-14-pane-exceptions" className="flex min-h-0 flex-1 flex-col pt-3">
      <DataGrid<SodException>
        name="sod-exceptions"
        title={t("access.sod.exceptions.grid")}
        errorTitle={t("access.sod.exceptions.loadError")}
        countLabel={(value, formatted) =>
          t("access.sod.exceptions.count", { count: value, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(exception) => exception.id}
        rowLabel={(exception) => `${exception.member_name} ${exception.sod_rule_code}`}
        testIdPrefix="SF-14"
        rowTestKey={(exception) => exception.id}
        onTotalChange={(next) => setTotal(next?.count)}
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={countLabel}
            testId="SF-14-filter-bar-exceptions"
          />
        }
        emptyState={
          <EmptyState
            title={t("access.sod.exceptions.empty.title")}
            description={t("access.sod.exceptions.empty.description")}
          />
        }
        noResults={
          <EmptyState
            title={t("access.sod.exceptions.noResults.title")}
            description={t("access.sod.exceptions.noResults.description")}
          />
        }
      />
      {revoking === null ? null : (
        <RevokeExceptionDialog
          exception={revoking}
          onClose={() => {
            setRevoking(null);
          }}
        />
      )}
    </div>
  );
}

/** SCREENS_B §9.12 "Revoke exception" (SB-R-05): the consequence, a reason and the Danger action. */
export function RevokeExceptionDialog({
  exception,
  onClose,
}: {
  readonly exception: SodException;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const revoke = useCommand<SodException>({
    method: "POST",
    path: sodExceptionRevokePath(exception.id),
    invalidates: [EVERY_SOD_EXCEPTION],
  });
  const params = { name: exception.member_name, rule: exception.sod_rule_code };
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await revoke.submit({ reason: reason.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("access.sod.exceptions.revoked", params) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("access.sod.exceptions.revokeDialog.title", params)}
      description={t("access.sod.exceptions.revokeDialog.description")}
      primaryAction={{
        label: t("access.sod.exceptions.revokeDialog.confirm"),
        destructive: true,
        form: formId,
      }}
      submitting={revoke.pending}
      onClose={onClose}
      testId="SF-14-dialog-revoke-exception"
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
