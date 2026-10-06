// SF-13:ssp-book-version SSP book version editor (SCREENS §11.0 lifecycle stepper "Draft · Approval ·
// Approved", header commands and author notice; §11.4 header, meta, entries grid, bands drawer, diff,
// versions and study panels, submission banners and test hooks; §0.4 RT-66; DESIGN_SYSTEM DS-CMP-06,
// DS-CMP-09, DS-CMP-10, DS-CMP-16, DS-CMP-18, DS-CMP-19, DS-CMP-21; 04 API-R-26, API-R-12 `POST /files`
// purpose `SSP_STUDY`, `GET, POST /attachments`, `POST /attachments/{id}/void`; BUILD_SPEC RFD-24).
// Breadcrumb "Policies / SSP books / <code>", the Policies route tabs with "SSP books" current, the
// record header (book name, version select, E-12 chip, `v<n>`), the commands for `ssp.create`: `DRAFT`
// "Submit for approval" (`If-Match`), `SUBMITTED` "Withdraw" for the preparer, any other status "New
// draft version" copying this version. A refused submission shows ERR-10 "Attach the SSP study before
// submitting this version.", ERR-32 with the server copy, or ERR-09. Entries, bands, meta and the study
// change only while `DRAFT`. The range findings column and the warnings acknowledgement are not built:
// no API serves the findings of an entry (XR-14; L4-5-Q-54).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type EditOutcome,
  type GridColumn,
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
import { controlClass, Field } from "../../components/form/Field";
import { ReasonField } from "../../components/form/ReasonField";
import { Select } from "../../components/form/Select";
import { Switch } from "../../components/form/Switch";
import { Num, SignedFigures } from "../../components/money/Num";
import { RecordHeader } from "../../components/record/RecordHeader";
import { type Step, Stepper } from "../../components/record/Stepper";
import { withPane } from "../../components/record/pane-params";
import { PanelTabs, type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip, statusMessageKey } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { type CommandKeys, useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem, fieldErrorsOf, readProblem } from "../../lib/api/problems";
import { type Approval, fetchApproval } from "../../lib/api/queries/approvals";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  ATTACHMENTS_PATH,
  type Attachment,
  BAND_DIMENSIONS,
  type BandDimension,
  bandDimensionLabel,
  type DiffField,
  diffBaselineId,
  diffCount,
  diffRows,
  diffValue,
  type Distinctness,
  DISTINCTNESS,
  EDITOR_BASES,
  type EntryDiffRow,
  entryInput,
  entryKey,
  EVERY_SSP_BOOK,
  EVERY_SSP_BOOK_VERSION,
  fetchAllSspEntries,
  fetchSspBook,
  fetchSspBookVersion,
  fetchSspBookVersions,
  fetchSspDiff,
  fetchSspEntriesPage,
  fetchStudyAttachments,
  percentTextToRatio,
  primaryBand,
  QUANTITY_UNITS,
  quantityUnitLabel,
  ratioToPercentText,
  requiresExplicitBasis,
  SSP_BOOKS_PATH,
  SSP_CREATE_PERMISSION,
  SSP_METHODS,
  SSP_READ_PERMISSION,
  type SspBook,
  sspBookKey,
  type SspBookVersion,
  sspBookVersionKey,
  sspBookVersionPath,
  sspBookVersionRoute,
  sspBookVersionsKey,
  sspDiffKey,
  sspDistinctnessLabel,
  type SspEntry,
  type SspEntryInputWithUnit,
  type SspEntryWithUnit,
  sspEntriesKey,
  type SspMethod,
  sspMethodLabel,
  type SspQuantityUnit,
  type SspValueBasisAll,
  STUDY_REQUIRED_SLUG,
  STUDY_SUBJECT_TYPE,
  studyAttachmentsKey,
  uploadFile,
  valueBasisLabel,
  versionLabel,
} from "../../lib/api/queries/ssp-books";
import {
  fetchActiveProducts,
  fetchTenantCurrencies,
  productsKey,
  sspRunRoute,
  tenantCurrenciesKey,
  useCurrencyReference,
} from "../../lib/api/queries/ssp-calculator";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import { useFieldRefusals } from "../../lib/api/refusals";
import {
  formatDate,
  formatList,
  formatNumber,
  formatRate,
  formatTimestamp,
  NO_VALUE,
  percentParts,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { POLICY_TABS } from "./revenue";
import { postCommand, problemText, SspAccessLimited } from "./ssp-books";

/** SCREENS §11.4 panel tabs, `pane=entries|diff|versions|study`; the default omits `pane`. */
export const SSP_PANES = ["entries", "diff", "versions", "study"] as const;
export type SspPane = (typeof SSP_PANES)[number];

export const DRAWER_ENTRY = "entry";
export const DRAWER_NEW_ENTRY = "new-entry";
export const DRAWER_BANDS = "bands";

/** 04 API-C-13 ERR-09: a change to a version that is no longer `DRAFT`. */
const FROZEN_SLUG = "configuration-frozen";
/** SCREENS §11.4 entries grid columns hidden by default. */
const HIDDEN_COLUMNS: readonly string[] = [
  "basis",
  "quantityUnit",
  "unitListPrice",
  "midpointDiscount",
  "revenueAccount",
];
const STUDY_PURPOSE = "SSP_STUDY";
const DECIMAL = /^-?\d+(?:\.\d+)?$/;

export function sspPaneOf(value: string | null): SspPane {
  return SSP_PANES.find((pane) => pane === value) ?? "entries";
}

/** The approvers who decided a request, in step order, each once. */
export function approverNames(approval: Approval | undefined): readonly string[] {
  const names: string[] = [];
  for (const step of approval?.steps ?? []) {
    for (const decision of step.decisions) {
      if (!names.includes(decision.approver.display_name)) {
        names.push(decision.approver.display_name);
      }
    }
  }
  return names;
}

/** SCREENS §11.0 lifecycle stepper for SSP book versions: "Draft · Approval · Approved". */
export function sspLifecycleSteps(
  version: SspBookVersion,
  approval: Approval | undefined,
): { readonly steps: readonly Step[]; readonly currentId: string } {
  const order: Readonly<Record<SspBookVersion["status"], number>> = {
    DRAFT: 0,
    TESTED: 0,
    SUBMITTED: 1,
    REJECTED: 1,
    WITHDRAWN: 1,
    APPROVED: 2,
    PUBLISHED: 2,
    SUPERSEDED: 2,
    // E-12 VOIDED is a discarded estimate version only (04 rev 1.210); no version shown here takes it.
    VOIDED: 0,
  };
  const reached = order[version.status];
  const approvers = approverNames(approval);
  let approvalCaption: string | undefined;
  if (version.status === "SUBMITTED") {
    approvalCaption = t("policies.lifecycle.pending");
  } else if (reached === 2 && approvers.length > 0) {
    approvalCaption = t("policies.lifecycle.approvedBy", { name: approvers.join(", ") });
  } else if (version.status === "REJECTED") {
    approvalCaption = t("policies.lifecycle.rejected");
  } else if (version.status === "WITHDRAWN") {
    approvalCaption = t("policies.lifecycle.withdrawn");
  }
  const state = (index: number): Step["state"] => {
    if (index < reached || reached === 2) {
      return "complete";
    }
    if (index > reached) {
      return "pending";
    }
    if (version.status === "REJECTED") {
      return "error";
    }
    return version.status === "WITHDRAWN" ? "skipped" : "current";
  };
  const steps: Step[] = [
    {
      id: "draft",
      label: t("policies.lifecycle.draft"),
      state: state(0),
      caption: t("policies.lifecycle.edited", {
        date: formatDate(timestampDate(version.updated_at)),
      }),
    },
    {
      id: "approval",
      label: t("policies.lifecycle.approval"),
      state: state(1),
      caption: approvalCaption,
    },
    {
      id: "approved",
      label: t("policies.sspVersion.lifecycle.approved"),
      state: state(2),
      caption:
        version.effective_from_date === null
          ? undefined
          : t("policies.lifecycle.effective", { date: formatDate(version.effective_from_date) }),
    },
  ];
  const currentId = (["draft", "approval", "approved"] as const)[reached] ?? "draft";
  return { steps, currentId };
}

/** The screen's own sentence for a refusal's slug (ERR-10, ERR-09), where it has one. */
function slugTitle(problem: ApiProblem): string | undefined {
  switch (problem.slug) {
    case STUDY_REQUIRED_SLUG:
      return t("policies.sspVersion.studyRequired");
    case FROZEN_SLUG:
      return t("policies.version.frozen");
    default:
      return undefined;
  }
}

/** The banner title of a refused command: ERR-10, ERR-09, else the problem's copy (ERR-32). */
export function commandProblemTitle(problem: ApiProblem): string {
  return slugTitle(problem) ?? problem.detail ?? problem.title;
}

/** The API members the fields of the version's meta form send (DG-FE-06 rev 1.228). */
const META_MEMBERS = {
  legacy_version_label: ["legacy_version_label"],
  effective_from_date: ["effective_from_date"],
  methodology_label: ["methodology_label"],
} as const;

function allEntriesKey(versionId: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { id: versionId, view: "all-entries" });
}

async function invalidateAll(
  queryClient: ReturnType<typeof useQueryClient>,
  keys: readonly QueryKey[],
): Promise<void> {
  await Promise.all(keys.map((key) => queryClient.invalidateQueries({ queryKey: key })));
}

/** An upsert refusal keeps the API's field findings (`entries[i].<member>`), so the editor can place them. */
type UpsertOutcome = EditOutcome & { readonly fields?: Readonly<Record<string, string>> };

/**
 * `POST /ssp-book-versions/{id}/entries` under the key `keys` holds for these entries (DG-FE-05 rev
 * 1.156). A command that got no answer is an outcome too: the editor says so and keeps its input, and
 * the same entries saved again carry the same key.
 */
async function upsertEntries(
  keys: CommandKeys,
  versionId: string,
  entries: readonly SspEntryInputWithUnit[],
): Promise<UpsertOutcome> {
  let response: Response;
  try {
    response = await keys.send("POST", `${sspBookVersionPath(versionId)}/entries`, {
      body: { entries },
    });
  } catch {
    return { ok: false, message: t("common.command.noAnswer") };
  }
  if (response.ok) {
    return { ok: true };
  }
  const problem = await readProblem(response);
  const fields = fieldErrorsOf(problem);
  const [first] = Object.values(fields);
  return { ok: false, message: first ?? commandProblemTitle(problem), fields };
}

/** The editor field that an API finding at `entries[0].<member>` belongs to (SCREENS §11.4 rows 5 and 5a). */
const ENTRY_FIELD_OF: Readonly<Record<string, string>> = {
  "entries[0].value_basis": "basis",
  "entries[0].quantity_unit": "quantity_unit",
};

export interface PolicyRecordNavProps {
  /** The `policies.tabs` key of the list the record belongs to. */
  readonly tabKey: string;
  /** The current crumb: a code or a name. */
  readonly current: string;
  readonly mono?: boolean;
}

/** SCREENS §11.0: breadcrumb "Policies / <tab label> / <code>" and the route tabs, list tab current. */
export function PolicyRecordNav({ tabKey, current, mono = false }: PolicyRecordNavProps) {
  const built = useBuiltPaths();
  const access = useAccess();
  const location = useLocation();
  const home = POLICY_TABS.find((tab) => tab.key === tabKey);
  const tabs: RouteTab[] = POLICY_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`policies.tabs.${tab.key}`),
    to: tab.key === tabKey ? `${location.pathname}${location.search}` : tab.path,
    end: true,
  }));
  return (
    <div className="flex flex-col gap-3">
      <nav aria-label={t("common.record.breadcrumb")}>
        <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
          <li className="flex items-center gap-1.5">
            <Link to="/policies" className="hover:text-fg-1 hover:underline">
              {t("policies.title")}
            </Link>
            <span aria-hidden="true">/</span>
          </li>
          {home === undefined || !built.has(home.path) ? null : (
            <li className="flex items-center gap-1.5">
              <Link to={home.path} className="hover:text-fg-1 hover:underline">
                {t(`policies.tabs.${home.key}`)}
              </Link>
              <span aria-hidden="true">/</span>
            </li>
          )}
          <li aria-current="page" className={mono ? "font-mono text-mono-sm" : undefined}>
            {current}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("policies.tabs.label")} tabs={tabs} />}
    </div>
  );
}

export function SspBookVersionEditor() {
  const { bookId = "", versionId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const navigate = useNavigate();
  const read = access.holdsAnywhere(SSP_READ_PERMISSION);
  const version = useQuery({
    queryKey: sspBookVersionKey(versionId),
    queryFn: () => fetchSspBookVersion(versionId),
    enabled: read,
  });
  const book = useQuery({
    queryKey: sspBookKey(bookId),
    queryFn: () => fetchSspBook(bookId),
    enabled: read,
  });
  const region = t("policies.sspVersion.region");

  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  if (!read) {
    return <SspAccessLimited />;
  }
  const failure = version.error ?? book.error;
  const notFound = (
    <EmptyState
      title={t("policies.sspVersion.notFound.title")}
      description={t("policies.version.notFound.description")}
      action={{
        label: t("policies.sspBooks.notFound.action"),
        onAction: () => void navigate("/policies/ssp-books"),
      }}
    />
  );
  if (failure !== null) {
    if (failure instanceof ApiProblem && failure.status === 404) {
      return notFound;
    }
    return (
      <Banner
        tone="negative"
        title={t("policies.sspVersion.loadError")}
        headingLevel={2}
        actions={
          <Button
            variant="link"
            onClick={() => {
              void version.refetch();
              void book.refetch();
            }}
          >
            {t("policies.retry")}
          </Button>
        }
      >
        {problemText(failure)}
      </Banner>
    );
  }
  if (version.data === undefined || book.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  if (version.data.ssp_book_id !== book.data.id) {
    return notFound;
  }
  return (
    <SspVersionView
      key={version.data.id}
      book={book.data}
      version={version.data}
      me={me.data}
      create={access.holdsAnywhere(SSP_CREATE_PERMISSION)}
    />
  );
}

interface SspVersionViewProps {
  readonly book: SspBook;
  readonly version: SspBookVersion;
  readonly me: Me;
  readonly create: boolean;
}

function statusWord(status: SspBookVersion["status"]): string {
  const spec = chipFor("E-12", status);
  return spec === null ? status : t(statusMessageKey(spec.status));
}

function SspVersionView({ book, version, me, create }: SspVersionViewProps) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const pane = sspPaneOf(params.get("pane"));
  const drawer = params.get("drawer");
  const row = params.get("row");
  const editable = create && version.status === "DRAFT";
  const versions = useQuery({
    queryKey: sspBookVersionsKey(book.id),
    queryFn: () => fetchSspBookVersions(book.id),
  });
  const approvalId = version.approval_request_id;
  const approval = useQuery({
    queryKey: queryKey("approvals", "tenant", { id: approvalId ?? "" }),
    queryFn: () => fetchApproval(approvalId ?? ""),
    enabled: approvalId !== null,
    retry: false,
  });
  const study = useQuery({
    queryKey: studyAttachmentsKey(version.id),
    queryFn: () => fetchStudyAttachments(version.id),
  });
  const entries = useQuery({
    queryKey: allEntriesKey(version.id),
    queryFn: () => fetchAllSspEntries(version.id),
  });
  // DS-FMT-03: the entries' unit rates render once their currencies are registered.
  const currencies = useCurrencyReference([
    ...(book.currency === null ? [] : [book.currency]),
    ...(entries.data ?? []).map((item) => item.currency),
  ]);
  const baselineId =
    versions.data === undefined ? null : diffBaselineId(book, version, versions.data);
  const diff = useQuery({
    queryKey: sspDiffKey(version.id, baselineId ?? ""),
    queryFn: () => fetchSspDiff(version.id, baselineId ?? ""),
    enabled: baselineId !== null,
  });
  const invalidates: readonly QueryKey[] = [
    EVERY_SSP_BOOK_VERSION,
    EVERY_SSP_BOOK,
    studyAttachmentsKey(version.id),
    queryKey("approvals", "tenant"),
  ];
  const versionPath = sspBookVersionPath(version.id);
  const submitVersion = useCommand<SspBookVersion>({
    method: "POST",
    path: `${versionPath}/submit`,
    invalidates,
  });
  const withdraw = useCommand<SspBookVersion>({
    method: "POST",
    path: `${versionPath}/withdraw`,
    invalidates,
  });
  const newDraft = useCommand<SspBookVersion>({
    method: "POST",
    path: `${SSP_BOOKS_PATH}/${book.id}/versions`,
    invalidates: [EVERY_SSP_BOOK, EVERY_SSP_BOOK_VERSION],
  });
  const commands = [submitVersion, withdraw, newDraft];
  const precondition = commands.find((command) => command.banner !== null)?.banner ?? null;
  const failed = commands.find((command) => command.problem !== null)?.problem ?? null;
  const preparerId = approval.data?.preparer.id ?? version.created_by.id;
  const authoredByViewer = preparerId === me.user.id;
  const label = versionLabel(version);
  const identity = { code: book.code, label };

  const setPane = (next: string) => {
    setParams(
      (current) => {
        // The lists of this screen live in its panes: their parameters leave with the pane (F4).
        const copy = withPane(current, next === "entries" ? null : next);
        copy.delete("drawer");
        copy.delete("row");
        return copy;
      },
      { replace: true },
    );
  };
  const openDrawer = (name: string, id: string | null = null) => {
    setParams((current) => {
      const copy = new URLSearchParams(current);
      copy.set("drawer", name);
      if (id === null) {
        copy.delete("row");
      } else {
        copy.set("row", id);
      }
      return copy;
    });
  };
  const closeDrawer = () => {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        copy.delete("drawer");
        copy.delete("row");
        return copy;
      },
      { replace: true },
    );
  };

  const doSubmit = async () => {
    const outcome = await submitVersion.submit({}, { ifMatch: rowIfMatch(version.row_version) });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.sspVersion.submitted", identity) });
    }
  };
  const doWithdraw = async () => {
    const outcome = await withdraw.submit({});
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.sspVersion.withdrawn", identity) });
    }
  };
  const doNewDraft = async () => {
    const outcome = await newDraft.submit({
      copy_from_version_id: version.id,
      methodology_label: version.methodology_label,
    });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.sspVersion.draftCreated", {
          code: book.code,
          version: outcome.data.version_no,
        }),
      });
      void navigate(sspBookVersionRoute(book.id, outcome.data.id));
    }
  };

  let actions: ReactNode = null;
  if (create) {
    switch (version.status) {
      case "DRAFT":
      case "TESTED":
        actions = (
          <Button
            variant="primary"
            loading={submitVersion.pending}
            disabledReason={
              book.resolution_mode === "EFFECTIVE_DATE" && version.effective_from_date === null
                ? t("policies.version.effectiveRequired")
                : undefined
            }
            onClick={() => void doSubmit()}
          >
            {t("policies.version.submit")}
          </Button>
        );
        break;
      case "SUBMITTED":
        actions = authoredByViewer ? (
          <Button variant="secondary" loading={withdraw.pending} onClick={() => void doWithdraw()}>
            {t("policies.version.withdraw")}
          </Button>
        ) : null;
        break;
      default:
        actions = (
          <Button variant="primary" loading={newDraft.pending} onClick={() => void doNewDraft()}>
            {t("policies.version.newDraft")}
          </Button>
        );
    }
  }

  const banners: ReactNode[] = [];
  if (version.status === "SUBMITTED") {
    banners.push(
      <Banner key="waiting" tone="info" title={t("policies.sspVersion.waiting", { label })} />,
    );
    if (authoredByViewer) {
      banners.push(<Banner key="author" tone="info" title={t("policies.version.authorNotice")} />);
    }
  }
  if (precondition !== null) {
    banners.push(<Banner key="precondition" tone="warning" announce="live" title={precondition} />);
  } else if (failed !== null) {
    banners.push(
      <Banner
        key="problem"
        tone={failed.slug === FROZEN_SLUG ? "warning" : "negative"}
        announce="live"
        title={commandProblemTitle(failed)}
      />,
    );
  }

  const statusSpec = chipFor("E-12", version.status);
  const lifecycle = sspLifecycleSteps(version, approval.data);
  const changed = diff.data === undefined ? 0 : diffCount(diff.data);
  const tabs = [
    { id: "entries", label: t("policies.sspVersion.panes.entries"), count: version.entry_count },
    {
      id: "diff",
      label:
        changed === 0
          ? t("policies.sspVersion.panes.diff")
          : t("policies.sspVersion.panes.diffChanged", {
              count: changed,
              formatted: formatNumber(changed, { kind: "count" }),
            }),
    },
    {
      id: "versions",
      label: t("policies.sspVersion.panes.versions"),
      count: versions.data?.length,
    },
    { id: "study", label: t("policies.sspVersion.panes.study"), count: study.data?.length },
  ];
  const menuItems = (versions.data ?? [version]).map((item) => ({
    id: item.id,
    label: t("policies.sspVersion.select", {
      label: versionLabel(item),
      status: statusWord(item.status),
    }),
    onSelect: () => void navigate(sspBookVersionRoute(book.id, item.id)),
  }));

  let panel: ReactNode;
  switch (pane) {
    case "entries":
      panel = (
        <EntriesPane
          version={version}
          editable={editable}
          invalidates={invalidates}
          onOpen={openDrawer}
        />
      );
      break;
    case "diff":
      panel = (
        <DiffPane
          version={version}
          baselineId={baselineId}
          baselineKnown={versions.data !== undefined}
          diff={diff.data}
          diffError={diff.error}
          entries={entries.data}
        />
      );
      break;
    case "versions":
      panel = <VersionsPane book={book} version={version} versions={versions.data} />;
      break;
    case "study":
      panel = (
        <StudyPane
          version={version}
          editable={editable}
          attachments={study.data}
          invalidates={invalidates}
        />
      );
      break;
  }

  const selected = row === null ? undefined : entries.data?.find((entry) => entry.id === row);
  const referenceError = entries.error ?? currencies.error;
  if (referenceError !== null) {
    return (
      <Banner tone="negative" title={t("policies.sspVersion.loadError")} headingLevel={2}>
        {problemText(referenceError)}
      </Banner>
    );
  }
  if (entries.data === undefined || currencies.data === undefined) {
    return <Skeleton region={t("policies.sspVersion.region")} shape="rows" count={8} />;
  }

  return (
    <div className="flex w-full flex-col gap-4">
      <PolicyRecordNav tabKey="sspBooks" current={book.code} mono />
      <RecordHeader
        title={book.name}
        chips={
          <>
            <Menu
              label={t("policies.sspVersion.select", {
                label,
                status: statusWord(version.status),
              })}
              items={menuItems}
              variant="secondary"
              size="sm"
            />
            {statusSpec === null ? null : <StatusChip status={statusSpec.status} />}
            <OutlineChip label={t("policies.version.number", { version: version.version_no })} />
          </>
        }
        actions={actions}
        banner={
          banners.length === 0 ? undefined : <div className="flex flex-col gap-2">{banners}</div>
        }
        tracker={
          <Stepper
            label={t("policies.lifecycle.label")}
            steps={lifecycle.steps}
            currentId={lifecycle.currentId}
          />
        }
      />
      {version.status === "SUBMITTED" && approval.data !== undefined ? (
        <RoutingPanel approval={approval.data} />
      ) : null}
      <SspVersionMeta
        book={book}
        version={version}
        approval={approval.data}
        editable={editable}
        study={study.data}
        invalidates={invalidates}
      />
      <PanelTabs
        label={t("policies.sspVersion.panes.label")}
        tabs={tabs}
        selectedId={pane}
        onChange={setPane}
      >
        {panel}
      </PanelTabs>
      {drawer === DRAWER_ENTRY && selected !== undefined ? (
        <EntryDrawer
          key={`${selected.id}:${String(editable)}`}
          book={book}
          version={version}
          entry={selected}
          editable={editable}
          invalidates={invalidates}
          onClose={closeDrawer}
        />
      ) : null}
      {drawer === DRAWER_NEW_ENTRY && editable ? (
        <EntryDrawer
          key="new"
          book={book}
          version={version}
          entry={null}
          editable
          invalidates={invalidates}
          onClose={closeDrawer}
        />
      ) : null}
      {drawer === DRAWER_BANDS && selected !== undefined ? (
        <BandsDrawer
          key={`bands:${selected.id}:${String(editable)}`}
          version={version}
          entry={selected}
          editable={editable}
          invalidates={invalidates}
          onClose={closeDrawer}
        />
      ) : null}
    </div>
  );
}

/** SCREENS §11.4 "After submission": the routing panel listing the request's steps. */
function RoutingPanel({ approval }: { readonly approval: Approval }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2 px-[var(--gutter)]">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("policies.sspVersion.routing.title")}
      </h2>
      <ol className="flex flex-col gap-1 text-body-sm text-fg-2">
        {approval.steps.map((step) => (
          <li key={step.step_no}>
            {t("policies.sspVersion.routing.step", {
              position: formatNumber(step.step_no),
              name: step.name,
              recorded: formatNumber(step.decisions.length),
              required: formatNumber(step.min_approvers),
            })}
          </li>
        ))}
      </ol>
    </section>
  );
}

interface SspVersionMetaProps {
  readonly book: SspBook;
  readonly version: SspBookVersion;
  readonly approval: Approval | undefined;
  readonly editable: boolean;
  readonly study: readonly Attachment[] | undefined;
  readonly invalidates: readonly QueryKey[];
}

/** SCREENS §11.4 Meta: a form while `DRAFT` for `ssp.create`; a definition list otherwise. */
function SspVersionMeta({
  book,
  version,
  approval,
  editable,
  study,
  invalidates,
}: SspVersionMetaProps) {
  const toast = useToast();
  const formId = useId();
  const helpId = useId();
  const [label, setLabel] = useState(version.legacy_version_label ?? "");
  const [typed, setTyped] = useState(
    version.effective_from_date === null ? "" : formatDate(version.effective_from_date),
  );
  const [date, setDate] = useState<string | null>(version.effective_from_date);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [methodology, setMethodology] = useState(version.methodology_label);
  const [methodologyChange, setMethodologyChange] = useState(version.is_methodology_change);
  const [local, setLocal] = useState<string | null>(null);
  const patch = useCommand<SspBookVersion>({
    method: "PATCH",
    path: sspBookVersionPath(version.id),
    invalidates,
  });
  const refusals = useFieldRefusals(patch.problem, META_MEMBERS);
  const approvers = approverNames(approval);
  const names = (study ?? []).map((item) => item.original_filename ?? item.sha256.slice(0, 12));
  const items: { readonly label: string; readonly value: ReactNode; readonly help?: string }[] = [
    ...(editable
      ? []
      : [
          {
            label: t("policies.sspVersion.meta.label"),
            value: version.legacy_version_label ?? NO_VALUE,
          },
          {
            label: t("policies.sspVersion.meta.effectiveFrom"),
            value: formatDate(version.effective_from_date),
          },
        ]),
    {
      label: t("policies.sspVersion.meta.effectiveTo"),
      value: formatDate(version.effective_to_date),
      help: t("policies.sspVersion.meta.effectiveToHelp"),
    },
    ...(editable
      ? []
      : [
          { label: t("policies.sspVersion.meta.methodology"), value: version.methodology_label },
          {
            label: t("policies.sspVersion.meta.methodologyChange"),
            value: t(version.is_methodology_change ? "common.grid.yes" : "common.grid.no"),
          },
        ]),
    { label: t("policies.sspVersion.meta.preparedBy"), value: version.created_by.display_name },
    {
      label: t("policies.meta.approver"),
      value: approvers.length === 0 ? NO_VALUE : approvers.join(", "),
    },
    {
      label: t("policies.sspVersion.meta.study"),
      value: names.length === 0 ? NO_VALUE : formatList(names, "unit"),
    },
    {
      label: t("policies.sspVersion.meta.calculatorRun"),
      value:
        version.ssp_calculator_run_id === null ? (
          NO_VALUE
        ) : (
          <Link
            to={sspRunRoute(version.ssp_calculator_run_id)}
            className="text-accent-fg hover:underline"
          >
            {t("policies.sspVersion.meta.openRun")}
          </Link>
        ),
    },
    {
      label: t("policies.meta.sha"),
      value:
        version.content_sha256 === null ? (
          NO_VALUE
        ) : (
          <span className="break-all font-mono text-mono-sm">{version.content_sha256}</span>
        ),
    },
  ];
  const list = (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-body-sm">
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-fg-3">{item.label}</dt>
          <dd className="text-fg-1">
            {item.value}
            {item.help === undefined ? null : (
              <span className="block text-caption text-fg-3">{item.help}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
  if (!editable) {
    return (
      <section aria-label={t("policies.meta.label")} className="px-[var(--gutter)]">
        {list}
      </section>
    );
  }
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (patch.pending || formatError !== null) {
      return;
    }
    if (methodology.trim() === "") {
      setLocal(t("policies.sspVersion.meta.methodologyRequired"));
      return;
    }
    setLocal(null);
    const outcome = await patch.submit(
      {
        legacy_version_label: label.trim() === "" ? null : label.trim(),
        effective_from_date: date,
        methodology_label: methodology.trim(),
        is_methodology_change: methodologyChange,
      },
      { ifMatch: rowIfMatch(version.row_version) },
    );
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("policies.sspVersion.meta.saved") });
    }
  };
  return (
    <section
      aria-label={t("policies.meta.label")}
      className="flex flex-col gap-4 px-[var(--gutter)]"
    >
      <form
        id={formId}
        aria-label={t("policies.sspVersion.meta.form")}
        noValidate
        onSubmit={(event) => void save(event)}
        className="flex flex-wrap items-end gap-4"
      >
        <Field
          name="version_label"
          label={t("policies.sspVersion.meta.label")}
          required={book.resolution_mode === "BY_LABEL"}
          optional={book.resolution_mode !== "BY_LABEL"}
          error={refusals.fields.legacy_version_label}
          width="period"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={label}
              onChange={(event) => {
                setLabel(event.target.value);
                refusals.edited("legacy_version_label");
              }}
              className={controlClass(refusals.fields.legacy_version_label !== null)}
            />
          )}
        </Field>
        <Field
          name="effective_from_date"
          label={t("policies.sspVersion.meta.effectiveFrom")}
          required={book.resolution_mode === "EFFECTIVE_DATE"}
          optional={book.resolution_mode !== "EFFECTIVE_DATE"}
          error={formatError ?? refusals.fields.effective_from_date}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={typed}
              onChange={(value) => {
                setTyped(value);
                refusals.edited("effective_from_date");
              }}
              onValue={setDate}
              onFormatError={setFormatError}
              invalid={formatError !== null}
            />
          )}
        </Field>
        <Field
          name="methodology_label"
          label={t("policies.sspVersion.meta.methodology")}
          required
          error={local ?? refusals.fields.methodology_label}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={methodology}
              onChange={(event) => {
                setMethodology(event.target.value);
                refusals.edited("methodology_label");
              }}
              className={controlClass(local !== null)}
            />
          )}
        </Field>
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              type="checkbox"
              checked={methodologyChange}
              aria-describedby={helpId}
              onChange={(event) => {
                setMethodologyChange(event.target.checked);
              }}
              className="size-4"
            />
            {t("policies.sspVersion.meta.methodologyChange")}
          </label>
          <span id={helpId} className="text-caption text-fg-3">
            {t("policies.sspVersion.meta.methodologyChangeHelp")}
          </span>
        </div>
        <Button variant="secondary" type="submit" loading={patch.pending}>
          {t("policies.sspVersion.meta.save")}
        </Button>
      </form>
      <RefusalBanner
        problem={refusals.banner}
        placed={refusals.placed}
        conflict={patch.banner}
        title={refusals.banner === null ? undefined : slugTitle(refusals.banner)}
      />
      {list}
    </section>
  );
}

interface EntriesPaneProps {
  readonly version: SspBookVersion;
  readonly editable: boolean;
  readonly invalidates: readonly QueryKey[];
  readonly onOpen: (drawer: string, id?: string | null) => void;
}

type BandMember = "low_value" | "mid_value" | "high_value" | "point_value";

/** SCREENS §11.4 entries grid (`SF-13:ssp-book-version#entries`), inline-editable while `DRAFT`. */
function EntriesPane({ version, editable, invalidates, onOpen }: EntriesPaneProps) {
  const queryClient = useQueryClient();
  const keys = useCommandKeys();
  const saveBand =
    (member: BandMember) =>
    async (entry: SspEntry, value: string): Promise<EditOutcome> => {
      if (entry.method === "legacy_range") {
        return { ok: false, message: t("policies.sspVersion.entries.derived") };
      }
      const band = primaryBand(entry);
      const next = {
        band_dimension: band?.band_dimension ?? ("NONE" as const),
        band_from: band?.band_from ?? null,
        band_to: band?.band_to ?? null,
        point_value: band?.point_value ?? null,
        low_value: band?.low_value ?? null,
        mid_value: band?.mid_value ?? null,
        high_value: band?.high_value ?? null,
        [member]: value,
      };
      const ranges =
        band === null ? [next] : entry.ranges.map((item) => (item === band ? next : item));
      const outcome = await upsertEntries(keys, version.id, [entryInput(entry, { ranges })]);
      if (outcome.ok) {
        await invalidateAll(queryClient, invalidates);
      }
      return outcome;
    };
  const rate = (entry: SspEntry, value: string | null) => (
    <span className={entry.method === "legacy_range" ? "text-fg-3" : undefined}>
      <Num value={value} kind="rate" currency={entry.currency} />
    </span>
  );
  const bandColumn = (
    id: string,
    member: BandMember,
    pick: (entry: SspEntry) => string | null,
  ): GridColumn<SspEntry> => ({
    id,
    header: t(`policies.sspVersion.entries.column.${id}`),
    kind: "number",
    value: pick,
    render: (entry) => rate(entry, pick(entry)),
    edit: editable ? { kind: "decimal", save: saveBand(member) } : undefined,
    width: 136,
  });
  const columns: readonly GridColumn<SspEntry>[] = [
    {
      id: "product",
      header: t("policies.sspVersion.entries.column.product"),
      kind: "identifier",
      value: (entry) => entry.product_code,
      href: (entry) => `?drawer=${DRAWER_ENTRY}&row=${entry.id}`,
      sortKey: "product_code",
      width: 160,
    },
    {
      id: "stratification",
      header: t("policies.sspVersion.entries.column.stratification"),
      kind: "text",
      value: (entry) => (entry.stratification === "" ? null : entry.stratification),
      width: 128,
    },
    {
      id: "currency",
      header: t("policies.sspVersion.entries.column.currency"),
      kind: "text",
      value: (entry) => entry.currency,
      render: (entry) => <span className="font-mono text-mono-sm">{entry.currency}</span>,
      width: 112,
    },
    {
      id: "method",
      header: t("policies.sspVersion.entries.column.method"),
      kind: "text",
      value: (entry) => sspMethodLabel(entry.method),
      width: 160,
    },
    {
      id: "basis",
      header: t("policies.sspVersion.entries.column.basis"),
      kind: "text",
      value: (entry) => valueBasisLabel(entry.value_basis),
      width: 144,
    },
    {
      id: "quantityUnit",
      header: t("policies.sspVersion.entries.column.quantityUnit"),
      kind: "text",
      value: (entry) => {
        const unit = (entry as SspEntryWithUnit).quantity_unit ?? null;
        return unit === null ? null : quantityUnitLabel(unit);
      },
      width: 144,
    },
    {
      id: "unitListPrice",
      header: t("policies.sspVersion.entries.column.unitListPrice"),
      kind: "number",
      value: (entry) => entry.unit_list_price,
      render: (entry) => (
        <Num value={entry.unit_list_price} kind="rate" currency={entry.currency} />
      ),
      width: 144,
    },
    {
      id: "midpointDiscount",
      header: t("policies.sspVersion.entries.column.midpointDiscount"),
      kind: "number",
      value: (entry) => entry.midpoint_discount_ratio,
      render: (entry) => <Num value={entry.midpoint_discount_ratio} kind="share" />,
      width: 160,
    },
    {
      id: "range",
      header: t("policies.sspVersion.entries.column.range"),
      kind: "number",
      value: (entry) => entry.range_ratio,
      render: (entry) => <Num value={entry.range_ratio} kind="share" />,
      width: 112,
    },
    bandColumn("low", "low_value", (entry) => primaryBand(entry)?.low_value ?? null),
    bandColumn("mid", "mid_value", (entry) => primaryBand(entry)?.mid_value ?? null),
    bandColumn("high", "high_value", (entry) => primaryBand(entry)?.high_value ?? null),
    bandColumn("point", "point_value", (entry) => primaryBand(entry)?.point_value ?? null),
    {
      id: "distinctness",
      header: t("policies.sspVersion.entries.column.distinctness"),
      kind: "text",
      value: (entry) => sspDistinctnessLabel(entry.distinctness),
      width: 128,
    },
    {
      id: "revenueAccount",
      header: t("policies.sspVersion.entries.column.revenueAccount"),
      kind: "text",
      value: (entry) => entry.revenue_account_code,
      render: (entry) =>
        entry.revenue_account_code === null ? (
          NO_VALUE
        ) : (
          <span className="font-mono text-mono-sm">{entry.revenue_account_code}</span>
        ),
      width: 160,
    },
    {
      id: "bands",
      header: t("policies.sspVersion.entries.column.bands"),
      kind: "number",
      value: (entry) => String(entry.ranges.length),
      render: (entry) => (
        <Button
          variant="link"
          size="sm"
          aria-label={t("policies.sspVersion.bands.open", { product: entry.product_code })}
          onClick={() => onOpen(DRAWER_BANDS, entry.id)}
        >
          {formatNumber(entry.ranges.length, { kind: "count" })}
        </Button>
      ),
      width: 96,
    },
  ];
  const source: GridSource<SspEntry> = {
    queryKey: sspEntriesKey(version.id),
    fetchPage: (cursor, sort) => fetchSspEntriesPage(version.id, cursor, sort),
  };
  return (
    <div className="flex h-120 min-h-0 flex-col pt-3">
      <DataGrid<SspEntry>
        name="ssp-entries"
        title={t("policies.sspVersion.entries.title")}
        headingLevel={3}
        countLabel={(count, formatted) =>
          t("policies.sspVersion.entries.count", { count, formatted })
        }
        columns={columns}
        defaultColumnState={initialColumnState(columns, HIDDEN_COLUMNS)}
        source={source}
        rowKey={(entry) => entry.id}
        rowLabel={(entry) => entry.product_code}
        editable={editable}
        testIdPrefix="SF-13"
        rowTestKey={(entry) =>
          entry.stratification === ""
            ? entry.product_code
            : `${entry.product_code}-${entry.stratification}`
        }
        toolbarActions={
          editable ? (
            <Button variant="secondary" size="sm" onClick={() => onOpen(DRAWER_NEW_ENTRY)}>
              {t("policies.sspVersion.entries.add")}
            </Button>
          ) : undefined
        }
        emptyState={
          <EmptyState
            title={t("policies.sspVersion.entries.empty.title")}
            description={t("policies.sspVersion.entries.empty.description")}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

/** A typed decimal: empty is null; otherwise the plain digits, or `undefined` when invalid. */
function decimalOf(text: string): string | null | undefined {
  const plain = text.trim().replace(/[\s,]/g, "");
  if (plain === "") {
    return null;
  }
  return DECIMAL.test(plain) ? plain : undefined;
}

/** A typed percent as the API ratio: empty is null, `undefined` when invalid. */
function ratioOf(text: string): string | null | undefined {
  if (text.trim() === "") {
    return null;
  }
  return percentTextToRatio(text) ?? undefined;
}

const DECIMAL_MEMBERS = [
  "unit_list_price",
  "midpoint_discount_ratio",
  "range_ratio",
  "low_value",
  "mid_value",
  "high_value",
  "point_value",
] as const;
type DecimalMember = (typeof DECIMAL_MEMBERS)[number];
const RATIO_MEMBERS: ReadonlySet<DecimalMember> = new Set([
  "midpoint_discount_ratio",
  "range_ratio",
]);
const MEMBER_LABEL: Readonly<Record<DecimalMember, string>> = {
  unit_list_price: "unitListPrice",
  midpoint_discount_ratio: "midpointDiscount",
  range_ratio: "range",
  low_value: "low",
  mid_value: "mid",
  high_value: "high",
  point_value: "point",
};

interface EntryDrawerProps {
  readonly book: SspBook;
  readonly version: SspBookVersion;
  readonly entry: SspEntry | null;
  readonly editable: boolean;
  readonly invalidates: readonly QueryKey[];
  readonly onClose: () => void;
}

/** SCREENS §11.4 entry: a definition list, or while `DRAFT` the entry form with "Save entry". */
function EntryDrawer({ book, version, entry, editable, invalidates, onClose }: EntryDrawerProps) {
  const toast = useToast();
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const formId = useId();
  const creating = entry === null;
  const products = useQuery({
    queryKey: productsKey(),
    queryFn: fetchActiveProducts,
    enabled: editable && creating,
  });
  const currencies = useQuery({
    queryKey: tenantCurrenciesKey(),
    queryFn: fetchTenantCurrencies,
    enabled: editable && creating,
  });
  const band = entry === null ? null : primaryBand(entry);
  const [product, setProduct] = useState<string | null>(entry?.product_code ?? null);
  const [stratification, setStratification] = useState(entry?.stratification ?? "");
  const [currency, setCurrency] = useState<string | null>(entry?.currency ?? book.currency);
  const [method, setMethod] = useState<SspMethod>(entry?.method ?? "observable");
  // SCREENS §11.4 rows 5 and 5a (D-97 (3)/(3a); row 5 rev 1.6, SSP-ADMISSION-R1): a stored entry keeps its
  // declared basis and unit; a new entry of a product the API marks `requires_explicit_ssp_basis` has no
  // default basis (the product's own `distinctness_default` is display-only), any other product keeps
  // "Amount"; the quantity unit exists only for a PER_INCREMENT basis.
  const stored = entry as SspEntryWithUnit | null;
  const [basisChoice, setBasisChoice] = useState<SspValueBasisAll | null>(
    stored?.value_basis ?? null,
  );
  const [unit, setUnit] = useState<SspQuantityUnit | null>(stored?.quantity_unit ?? null);
  const seriesProduct =
    creating && requiresExplicitBasis((products.data ?? []).find((item) => item.code === product));
  const basis: SspValueBasisAll | null = basisChoice ?? (seriesProduct ? null : "AMOUNT");
  const [distinctness, setDistinctness] = useState<Distinctness>(entry?.distinctness ?? "distinct");
  const [account, setAccount] = useState(entry?.revenue_account_code ?? "");
  const [values, setValues] = useState<Readonly<Record<DecimalMember, string>>>({
    unit_list_price: entry?.unit_list_price ?? "",
    midpoint_discount_ratio: ratioToPercentText(entry?.midpoint_discount_ratio ?? null),
    range_ratio: ratioToPercentText(entry?.range_ratio ?? null),
    low_value: band?.low_value ?? "",
    mid_value: band?.mid_value ?? "",
    high_value: band?.high_value ?? "",
    point_value: band?.point_value ?? "",
  });
  const [local, setLocal] = useState<Readonly<Record<string, string>>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [removing, setRemoving] = useState(false);
  const title = creating
    ? t("policies.sspVersion.entry.new")
    : t("policies.sspVersion.entry.title", { product: entry.product_code });

  if (!editable && entry !== null) {
    const rows: readonly (readonly [string, ReactNode])[] = [
      [t("policies.sspVersion.entries.column.product"), entry.product_code],
      [
        t("policies.sspVersion.entries.column.stratification"),
        entry.stratification === "" ? NO_VALUE : entry.stratification,
      ],
      [t("policies.sspVersion.entries.column.currency"), entry.currency],
      [t("policies.sspVersion.entries.column.method"), sspMethodLabel(entry.method)],
      [t("policies.sspVersion.entries.column.basis"), valueBasisLabel(entry.value_basis)],
      [
        t("policies.sspVersion.entries.column.quantityUnit"),
        stored?.quantity_unit == null ? NO_VALUE : quantityUnitLabel(stored.quantity_unit),
      ],
      [
        t("policies.sspVersion.entries.column.unitListPrice"),
        <Num key="price" value={entry.unit_list_price} kind="rate" currency={entry.currency} />,
      ],
      [
        t("policies.sspVersion.entries.column.midpointDiscount"),
        <Num key="discount" value={entry.midpoint_discount_ratio} kind="share" />,
      ],
      [
        t("policies.sspVersion.entries.column.range"),
        <Num key="range" value={entry.range_ratio} kind="share" />,
      ],
      ...(["low", "mid", "high", "point"] as const).map(
        (id) =>
          [
            t(`policies.sspVersion.entries.column.${id}`),
            <Num key={id} value={diffValue(entry, id)} kind="rate" currency={entry.currency} />,
          ] as const,
      ),
      [
        t("policies.sspVersion.entries.column.distinctness"),
        sspDistinctnessLabel(entry.distinctness),
      ],
      [
        t("policies.sspVersion.entries.column.revenueAccount"),
        entry.revenue_account_code ?? NO_VALUE,
      ],
      [
        t("policies.sspVersion.entries.column.bands"),
        formatNumber(entry.ranges.length, { kind: "count" }),
      ],
    ];
    return (
      <Drawer open title={title} wide initialFocus="title" onClose={onClose}>
        <div data-testid="SF-13-drawer-entry">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-body-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-fg-3">{label}</dt>
                <dd className="num text-fg-1">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Drawer>
    );
  }

  const setValue = (member: DecimalMember, text: string) => {
    setValues((current) => ({ ...current, [member]: text }));
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const found: Record<string, string> = {};
    if (product === null) {
      found.product = t("policies.sspVersion.entry.productRequired");
    }
    if (currency === null) {
      found.currency = t("policies.sspVersion.entry.currencyRequired");
    }
    if (basis === null) {
      found.basis = t("policies.sspVersion.entry.basisRequired");
    }
    if (basis === "PER_INCREMENT" && unit === null) {
      found.quantity_unit = t("policies.sspVersion.entry.quantityUnitRequired");
    }
    const parsed: Partial<Record<DecimalMember, string | null>> = {};
    for (const member of DECIMAL_MEMBERS) {
      const text = values[member];
      const value = RATIO_MEMBERS.has(member) ? ratioOf(text) : decimalOf(text);
      if (value === undefined) {
        found[member] = RATIO_MEMBERS.has(member)
          ? t("policies.sspVersion.entry.percentInvalid")
          : t("common.filters.numberInvalid");
      } else {
        parsed[member] = value;
      }
    }
    setLocal(found);
    if (Object.keys(found).length > 0 || product === null || currency === null || basis === null) {
      return;
    }
    const primary = {
      band_dimension: band?.band_dimension ?? ("NONE" as const),
      band_from: band?.band_from ?? null,
      band_to: band?.band_to ?? null,
      point_value: parsed.point_value ?? null,
      low_value: parsed.low_value ?? null,
      mid_value: parsed.mid_value ?? null,
      high_value: parsed.high_value ?? null,
    };
    const others = entry === null ? [] : entry.ranges.filter((item) => item !== band);
    const body: SspEntryInputWithUnit = {
      ...(entry === null ? {} : entryInput(entry)),
      product_code: product,
      stratification: stratification.trim(),
      currency,
      method,
      value_basis: basis,
      quantity_unit: basis === "PER_INCREMENT" ? unit : null,
      unit_list_price: parsed.unit_list_price ?? null,
      midpoint_discount_ratio: parsed.midpoint_discount_ratio ?? null,
      range_ratio: parsed.range_ratio ?? null,
      distinctness,
      revenue_account_code: account.trim() === "" ? null : account.trim(),
      ranges: method === "legacy_range" ? null : [primary, ...others],
    };
    setPending(true);
    setProblem(null);
    const outcome = await upsertEntries(keys, version.id, [body]);
    setPending(false);
    if (!outcome.ok) {
      // An API finding at entries[0].value_basis or entries[0].quantity_unit shows at its field (row 5a);
      // every other finding stays in the drawer banner.
      const placed: Record<string, string> = {};
      const rest: string[] = [];
      for (const [field, message] of Object.entries(outcome.fields ?? {})) {
        const target = ENTRY_FIELD_OF[field];
        if (target === undefined) {
          rest.push(message);
        } else {
          placed[target] = message;
        }
      }
      setLocal(placed);
      setProblem(
        Object.keys(placed).length > 0 && rest.length === 0 ? null : (rest[0] ?? outcome.message),
      );
      return;
    }
    await invalidateAll(queryClient, invalidates);
    toast.show({ tone: "positive", message: t("policies.sspVersion.entry.saved", { product }) });
    onClose();
  };

  const remove = async () => {
    if (entry === null) {
      return;
    }
    setPending(true);
    const response = await keys
      .send("DELETE", `${sspBookVersionPath(version.id)}/entries/${entry.id}`)
      .catch(() => null);
    setPending(false);
    setRemoving(false);
    if (response === null) {
      // No answer: the next press sends the removal under the same key (DG-FE-05).
      setProblem(t("common.command.noAnswer"));
      return;
    }
    if (!response.ok) {
      setProblem(commandProblemTitle(await readProblem(response)));
      return;
    }
    await invalidateAll(queryClient, invalidates);
    toast.show({
      tone: "positive",
      message: t("policies.sspVersion.entry.removed", { product: entry.product_code }),
    });
    onClose();
  };

  const decimalField = (member: DecimalMember) => {
    const key = MEMBER_LABEL[member];
    const ratio = RATIO_MEMBERS.has(member);
    return (
      <Field
        key={member}
        name={`entry_${member}`}
        label={t(`policies.sspVersion.entries.column.${key}`)}
        optional
        help={ratio ? t("policies.sspVersion.entry.percentHelp") : undefined}
        error={local[member] ?? null}
        width="money"
      >
        {(control) => (
          <input
            {...control}
            type="text"
            inputMode="decimal"
            value={values[member]}
            onChange={(event) => {
              setValue(member, event.target.value);
            }}
            className={`${controlClass(local[member] !== undefined)} num text-end`}
          />
        )}
      </Field>
    );
  };

  return (
    <>
      <Drawer
        open
        title={title}
        wide
        dirty
        submitting={pending}
        banner={problem === null ? undefined : <Banner tone="negative" title={problem} />}
        primaryAction={{ label: t("policies.sspVersion.entry.save"), form: formId }}
        onClose={onClose}
      >
        <form
          id={formId}
          noValidate
          data-testid="SF-13-drawer-entry"
          onSubmit={(event) => void submit(event)}
          className="flex flex-col gap-4"
        >
          <Field
            name="entry_product"
            label={t("policies.sspVersion.entries.column.product")}
            required
            error={local.product ?? null}
            width="text"
          >
            {(control) =>
              creating ? (
                <Combobox<string>
                  control={control}
                  options={(products.data ?? []).map((item) => ({
                    value: item.code,
                    label: `${item.code} · ${item.name}`,
                  }))}
                  value={product}
                  onChange={setProduct}
                  invalid={local.product !== undefined}
                />
              ) : (
                <input
                  {...control}
                  type="text"
                  readOnly
                  value={product ?? ""}
                  className={`${controlClass(false)} font-mono`}
                />
              )
            }
          </Field>
          <Field
            name="entry_stratification"
            label={t("policies.sspVersion.entries.column.stratification")}
            optional
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                readOnly={!creating}
                value={stratification}
                onChange={(event) => {
                  setStratification(event.target.value);
                }}
                className={controlClass(false)}
              />
            )}
          </Field>
          <Field
            name="entry_currency"
            label={t("policies.sspVersion.entries.column.currency")}
            required
            error={local.currency ?? null}
            width="period"
          >
            {(control) =>
              creating ? (
                <Select<string>
                  control={control}
                  options={(currencies.data ?? []).map((item) => ({
                    value: item.currency_code,
                    label: item.currency_code,
                  }))}
                  value={currency}
                  onChange={setCurrency}
                  invalid={local.currency !== undefined}
                />
              ) : (
                <input
                  {...control}
                  type="text"
                  readOnly
                  value={currency ?? ""}
                  className={`${controlClass(false)} font-mono`}
                />
              )
            }
          </Field>
          <Field
            name="entry_method"
            label={t("policies.sspVersion.entries.column.method")}
            required
            width="text"
          >
            {(control) => (
              <Select<SspMethod>
                control={control}
                options={SSP_METHODS.map((value) => ({ value, label: sspMethodLabel(value) }))}
                value={method}
                onChange={setMethod}
              />
            )}
          </Field>
          <Field
            name="entry_basis"
            label={t("policies.sspVersion.entries.column.basis")}
            required
            error={local.basis ?? null}
            width="text"
          >
            {(control) => (
              <Select<SspValueBasisAll>
                control={control}
                options={EDITOR_BASES.map((value) => ({ value, label: valueBasisLabel(value) }))}
                value={basis}
                placeholder={t("policies.sspVersion.entry.basisPlaceholder")}
                invalid={local.basis !== undefined}
                onChange={(value) => {
                  setBasisChoice(value);
                  if (value !== "PER_INCREMENT") {
                    setUnit(null);
                  }
                }}
              />
            )}
          </Field>
          {basis === "PER_INCREMENT" ? (
            <Field
              name="entry_quantity_unit"
              label={t("policies.sspVersion.entries.column.quantityUnit")}
              required
              help={t("policies.sspVersion.entry.quantityUnitHelp")}
              error={local.quantity_unit ?? null}
              width="text"
            >
              {(control) => (
                <Select<SspQuantityUnit>
                  control={control}
                  options={QUANTITY_UNITS.map((value) => ({
                    value,
                    label: quantityUnitLabel(value),
                  }))}
                  value={unit}
                  placeholder={t("policies.sspVersion.entry.quantityUnitPlaceholder")}
                  invalid={local.quantity_unit !== undefined}
                  onChange={setUnit}
                />
              )}
            </Field>
          ) : null}
          <div className="flex flex-wrap gap-4">
            {decimalField("unit_list_price")}
            {decimalField("midpoint_discount_ratio")}
            {decimalField("range_ratio")}
          </div>
          <div className="flex flex-wrap gap-4">
            {decimalField("low_value")}
            {decimalField("mid_value")}
            {decimalField("high_value")}
            {decimalField("point_value")}
          </div>
          <Field
            name="entry_distinctness"
            label={t("policies.sspVersion.entries.column.distinctness")}
            required
            width="text"
          >
            {(control) => (
              <Select<Distinctness>
                control={control}
                options={DISTINCTNESS.map((value) => ({
                  value,
                  label: sspDistinctnessLabel(value),
                }))}
                value={distinctness}
                onChange={setDistinctness}
              />
            )}
          </Field>
          <Field
            name="entry_revenue_account"
            label={t("policies.sspVersion.entries.column.revenueAccount")}
            optional
            width="text"
          >
            {(control) => (
              <input
                {...control}
                type="text"
                value={account}
                onChange={(event) => {
                  setAccount(event.target.value);
                }}
                className={`${controlClass(false)} font-mono`}
              />
            )}
          </Field>
          {creating ? null : (
            <div>
              <Button variant="secondary" onClick={() => setRemoving(true)}>
                {t("policies.sspVersion.entry.remove")}
              </Button>
            </div>
          )}
        </form>
      </Drawer>
      {removing && entry !== null ? (
        <Modal
          open
          variant="confirmation"
          title={t("policies.sspVersion.entry.removeTitle", { product: entry.product_code })}
          description={t("policies.sspVersion.entry.removeDescription")}
          primaryAction={{
            label: t("policies.sspVersion.entry.remove"),
            destructive: true,
            onAction: () => void remove(),
          }}
          submitting={pending}
          onClose={() => setRemoving(false)}
        />
      ) : null}
    </>
  );
}

interface BandRow {
  readonly key: string;
  readonly from: string;
  readonly to: string;
  readonly point: string;
  readonly low: string;
  readonly mid: string;
  readonly high: string;
}

const BAND_CELLS = ["from", "to", "point", "low", "mid", "high"] as const;
type BandCell = (typeof BAND_CELLS)[number];

interface BandsDrawerProps {
  readonly version: SspBookVersion;
  readonly entry: SspEntry;
  readonly editable: boolean;
  readonly invalidates: readonly QueryKey[];
  readonly onClose: () => void;
}

/** SCREENS §11.4 bands drawer: Band dimension; rows From, To, Point, Low, Mid, High (DS-FMT-13). */
function BandsDrawer({ version, entry, editable, invalidates, onClose }: BandsDrawerProps) {
  const toast = useToast();
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const formId = useId();
  const dimensionId = useId();
  const bandsEditable = editable && entry.method !== "legacy_range";
  const [dimension, setDimension] = useState<BandDimension>(
    entry.ranges[0]?.band_dimension ?? "NONE",
  );
  const [rows, setRows] = useState<readonly BandRow[]>(
    entry.ranges.map((band, index) => ({
      key: String(index),
      from: band.band_from ?? "",
      to: band.band_to ?? "",
      point: band.point_value ?? "",
      low: band.low_value ?? "",
      mid: band.mid_value ?? "",
      high: band.high_value ?? "",
    })),
  );
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const headers = BAND_CELLS.map((cell) => t(`policies.sspVersion.bands.column.${cell}`));

  const update = (key: string, cell: BandCell, text: string) => {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, [cell]: text } : row)));
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const ranges: NonNullable<SspEntryInputWithUnit["ranges"]> = [];
    for (const row of rows) {
      const parsed = BAND_CELLS.map((cell) => decimalOf(row[cell]));
      if (parsed.some((value) => value === undefined)) {
        setProblem(t("policies.sspVersion.bands.invalid"));
        return;
      }
      const [from, to, point, low, mid, high] = parsed as (string | null)[];
      ranges.push({
        band_dimension: dimension,
        band_from: from ?? null,
        band_to: to ?? null,
        point_value: point ?? null,
        low_value: low ?? null,
        mid_value: mid ?? null,
        high_value: high ?? null,
      });
    }
    setPending(true);
    setProblem(null);
    const outcome = await upsertEntries(keys, version.id, [entryInput(entry, { ranges })]);
    setPending(false);
    if (!outcome.ok) {
      setProblem(outcome.message);
      return;
    }
    await invalidateAll(queryClient, invalidates);
    toast.show({
      tone: "positive",
      message: t("policies.sspVersion.bands.saved", { product: entry.product_code }),
    });
    onClose();
  };

  const table = (
    <table className="w-full border-collapse text-body-sm">
      <caption className="pb-2 text-start text-title-sm text-fg-1">
        {t("policies.sspVersion.bands.title")}
      </caption>
      <thead>
        <tr className="border-b border-default bg-subtle">
          {headers.map((header) => (
            <th key={header} scope="col" className="px-2 py-2 text-end font-medium text-fg-2">
              {header}
            </th>
          ))}
          {bandsEditable ? (
            <th scope="col" className="px-2 py-2 text-end font-medium text-fg-2">
              <span className="sr-only">{t("policies.sspVersion.bands.column.actions")}</span>
            </th>
          ) : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, index) => (
          <tr key={row.key} className="border-b border-hairline">
            {BAND_CELLS.map((cell, column) => (
              <td key={cell} className="px-2 py-1.5 text-end">
                {bandsEditable ? (
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={t("policies.sspVersion.bands.cell", {
                      column: headers[column] ?? cell,
                      position: formatNumber(index + 1),
                    })}
                    value={row[cell]}
                    onChange={(event) => {
                      update(row.key, cell, event.target.value);
                    }}
                    className={`${controlClass(false)} num text-end`}
                  />
                ) : cell === "from" || cell === "to" ? (
                  <Num value={row[cell] === "" ? null : row[cell]} kind="quantity" />
                ) : (
                  <Num
                    value={row[cell] === "" ? null : row[cell]}
                    kind="rate"
                    currency={entry.currency}
                  />
                )}
              </td>
            ))}
            {bandsEditable ? (
              <td className="px-2 py-1.5 text-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setRows((current) => current.filter((item) => item.key !== row.key));
                  }}
                >
                  {t("policies.sspVersion.bands.remove", { position: formatNumber(index + 1) })}
                </Button>
              </td>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <Drawer
      open
      title={t("policies.sspVersion.bands.drawerTitle", { product: entry.product_code })}
      wide
      initialFocus={bandsEditable ? "field" : "title"}
      submitting={pending}
      banner={problem === null ? undefined : <Banner tone="negative" title={problem} />}
      primaryAction={
        bandsEditable ? { label: t("policies.sspVersion.bands.save"), form: formId } : undefined
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-13-drawer-bands"
        onSubmit={(event) => void save(event)}
        className="flex flex-col gap-4"
      >
        {entry.method === "legacy_range" ? (
          <p className="text-body-sm text-fg-3">{t("policies.sspVersion.bands.derived")}</p>
        ) : null}
        <div className="flex flex-col gap-1">
          <span id={dimensionId} className="text-body-sm font-medium text-fg-1">
            {t("policies.sspVersion.bands.dimension.label")}
          </span>
          {bandsEditable ? (
            <Field
              name="band_dimension"
              label={t("policies.sspVersion.bands.dimension.label")}
              width="text"
            >
              {(control) => (
                <Select<BandDimension>
                  control={control}
                  options={BAND_DIMENSIONS.map((value) => ({
                    value,
                    label: bandDimensionLabel(value),
                  }))}
                  value={dimension}
                  onChange={setDimension}
                />
              )}
            </Field>
          ) : (
            <span aria-labelledby={dimensionId} className="text-body-sm text-fg-1">
              {bandDimensionLabel(dimension)}
            </span>
          )}
        </div>
        {table}
        {bandsEditable ? (
          <div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setRows((current) => [
                  ...current,
                  {
                    key: String(Date.now()),
                    from: "",
                    to: "",
                    point: "",
                    low: "",
                    mid: "",
                    high: "",
                  },
                ]);
              }}
            >
              {t("policies.sspVersion.bands.add")}
            </Button>
          </div>
        ) : null}
      </form>
    </Drawer>
  );
}

function diffText(entry: SspEntry, field: DiffField): string {
  const value = diffValue(entry, field);
  switch (field) {
    case "method":
      return sspMethodLabel(entry.method);
    case "distinctness":
      return sspDistinctnessLabel(entry.distinctness);
    default:
      return value === null
        ? NO_VALUE
        : formatRate(value, { kind: "unit", currency: entry.currency });
  }
}

/** DS-FMT-31: the percent change of Mid with its sign. */
function DeltaPercent({ ratio }: { readonly ratio: string | null }) {
  if (ratio === null) {
    return <Num value={null} kind="percent" />;
  }
  const parts = percentParts(ratio);
  const signed =
    parts.sign === null && /[1-9]/.test(parts.body) ? { ...parts, sign: "plus" as const } : parts;
  return (
    <span className="num">
      <SignedFigures parts={signed} />
    </span>
  );
}

interface DiffPaneProps {
  readonly version: SspBookVersion;
  readonly baselineId: string | null;
  readonly baselineKnown: boolean;
  readonly diff: SspVersionDiffData | undefined;
  readonly diffError: unknown;
  readonly entries: readonly SspEntry[] | undefined;
}

type SspVersionDiffData = Awaited<ReturnType<typeof fetchSspDiff>>;

/** SCREENS §11.4 Diff panel: a DS-CMP-16 grid diff with "Was <value>" and the Mid delta. */
function DiffPane({ version, baselineId, baselineKnown, diff, diffError, entries }: DiffPaneProps) {
  const [showUnchanged, setShowUnchanged] = useState(false);
  if (baselineKnown && baselineId === null) {
    return (
      <div className="pt-3">
        <EmptyState
          title={t("policies.sspVersion.diff.noBaseline.title")}
          description={t("policies.sspVersion.diff.noBaseline.description")}
          headingLevel={3}
        />
      </div>
    );
  }
  if (diffError !== null) {
    return (
      <div className="pt-3">
        <Banner tone="negative" title={t("policies.sspVersion.diff.loadError")} headingLevel={3}>
          {problemText(diffError)}
        </Banner>
      </div>
    );
  }
  if (diff === undefined || (showUnchanged && entries === undefined)) {
    return <Skeleton region={t("policies.sspVersion.diff.title")} shape="rows" count={4} />;
  }
  const rows = diffRows(diff, entries ?? [], showUnchanged);
  const source: GridSource<EntryDiffRow> = {
    queryKey: queryKey("ssp-book-versions", "tenant", {
      id: version.id,
      view: "diff-rows",
      against: baselineId ?? "",
      unchanged: showUnchanged,
      digest: rows.map((item) => `${item.kind}:${entryKey(item.entry)}`).join(","),
    }),
    fetchPage: () =>
      Promise.resolve({
        items: rows,
        nextCursor: null,
        total: { count: rows.length, capped: false },
      }),
  };
  const cell = (item: EntryDiffRow, field: DiffField, content: ReactNode): ReactNode => {
    if (item.kind !== "changed" || !item.changed.has(field) || item.before === null) {
      return content;
    }
    return (
      <span
        className="truncate rounded-sm px-1 ring-1 ring-inset ring-warning-border"
        title={t("policies.changes.was", { value: diffText(item.before, field) })}
      >
        {content}
      </span>
    );
  };
  const rate = (item: EntryDiffRow, field: DiffField) =>
    cell(
      item,
      field,
      <Num value={diffValue(item.entry, field)} kind="rate" currency={item.entry.currency} />,
    );
  const columns: readonly GridColumn<EntryDiffRow>[] = [
    {
      id: "change",
      header: t("policies.changes.column.change"),
      kind: "status",
      value: (item) => item.kind,
      render: (item) =>
        item.kind === "unchanged" ? (
          <span className="text-fg-3">{t("policies.sspVersion.diff.unchanged")}</span>
        ) : (
          <>
            <span className="sr-only">{t(`common.diff.prefix.${item.kind}`)}</span>
            <OutlineChip label={t(`policies.changes.kind.${item.kind}`)} />
          </>
        ),
      width: 128,
    },
    {
      id: "product",
      header: t("policies.sspVersion.entries.column.product"),
      kind: "identifier",
      value: (item) => item.entry.product_code,
      width: 160,
    },
    {
      id: "stratification",
      header: t("policies.sspVersion.entries.column.stratification"),
      kind: "text",
      value: (item) => (item.entry.stratification === "" ? null : item.entry.stratification),
      width: 128,
    },
    {
      id: "currency",
      header: t("policies.sspVersion.entries.column.currency"),
      kind: "text",
      value: (item) => item.entry.currency,
      width: 112,
    },
    {
      id: "method",
      header: t("policies.sspVersion.entries.column.method"),
      kind: "text",
      value: (item) => sspMethodLabel(item.entry.method),
      render: (item) => cell(item, "method", sspMethodLabel(item.entry.method)),
      width: 160,
    },
    {
      id: "low",
      header: t("policies.sspVersion.entries.column.low"),
      kind: "number",
      value: (item) => diffValue(item.entry, "low"),
      render: (item) => rate(item, "low"),
      width: 136,
    },
    {
      id: "mid",
      header: t("policies.sspVersion.entries.column.mid"),
      kind: "number",
      value: (item) => diffValue(item.entry, "mid"),
      render: (item) => rate(item, "mid"),
      width: 136,
    },
    {
      id: "high",
      header: t("policies.sspVersion.entries.column.high"),
      kind: "number",
      value: (item) => diffValue(item.entry, "high"),
      render: (item) => rate(item, "high"),
      width: 136,
    },
    {
      id: "point",
      header: t("policies.sspVersion.entries.column.point"),
      kind: "number",
      value: (item) => diffValue(item.entry, "point"),
      render: (item) => rate(item, "point"),
      width: 136,
    },
    {
      id: "delta",
      header: t("policies.sspVersion.diff.column.delta"),
      kind: "number",
      value: (item) => item.midChangeRatio,
      render: (item) => <DeltaPercent ratio={item.midChangeRatio} />,
      width: 112,
    },
    {
      id: "distinctness",
      header: t("policies.sspVersion.entries.column.distinctness"),
      kind: "text",
      value: (item) => sspDistinctnessLabel(item.entry.distinctness),
      render: (item) => cell(item, "distinctness", sspDistinctnessLabel(item.entry.distinctness)),
      width: 128,
    },
  ];
  return (
    <div data-testid="SF-13-diff" className="flex flex-col gap-3 pt-3">
      <Switch
        label={t("policies.sspVersion.diff.showUnchanged")}
        checked={showUnchanged}
        onChange={setShowUnchanged}
      />
      <div className="flex h-120 min-h-0 flex-col">
        <DataGrid<EntryDiffRow>
          name="diff"
          title={t("policies.sspVersion.diff.title")}
          headingLevel={3}
          countLabel={(count, formatted) =>
            t("policies.sspVersion.entries.count", { count, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(item) => `${item.kind}:${entryKey(item.entry)}`}
          rowLabel={(item) => item.entry.product_code}
          testIdPrefix="SF-13"
          rowTestKey={(item) => `diff-${item.entry.product_code}`}
          emptyState={
            <EmptyState
              title={t("policies.changes.empty.title")}
              description={t("policies.sspVersion.diff.empty.description")}
              headingLevel={3}
            />
          }
        />
      </div>
    </div>
  );
}

interface VersionsPaneProps {
  readonly book: SspBook;
  readonly version: SspBookVersion;
  readonly versions: readonly SspBookVersion[] | undefined;
}

/** SCREENS §11.4 Versions panel: a static table of every version of the book. */
function VersionsPane({ book, version, versions }: VersionsPaneProps) {
  if (versions === undefined) {
    return <Skeleton region={t("policies.sspVersion.versions.title")} shape="rows" count={4} />;
  }
  const headers = [
    ["version", false],
    ["label", false],
    ["status", false],
    ["effectiveFrom", false],
    ["effectiveTo", false],
    ["entries", true],
    ["methodology", false],
    ["approvedAt", false],
  ] as const;
  return (
    <div className="pt-3">
      <table className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-title-sm text-fg-1">
          {t("policies.sspVersion.versions.title")}
        </caption>
        <thead>
          <tr className="border-b border-default bg-subtle">
            {headers.map(([key, end]) => (
              <th
                key={key}
                scope="col"
                className={`px-3 py-2 font-medium text-fg-2 ${end ? "text-end" : "text-start"}`}
              >
                {t(`policies.sspVersion.versions.column.${key}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {versions.map((item) => {
            const spec = chipFor("E-12", item.status);
            return (
              <tr key={item.id} className="border-b border-hairline">
                <th scope="row" className="px-3 py-2 text-start font-normal">
                  <Link
                    to={sspBookVersionRoute(book.id, item.id)}
                    aria-current={item.id === version.id ? "page" : undefined}
                    className="text-accent-fg hover:underline"
                  >
                    {t("policies.version.number", { version: item.version_no })}
                  </Link>
                </th>
                <td className="px-3 py-2">{item.legacy_version_label ?? NO_VALUE}</td>
                <td className="px-3 py-2">
                  {spec === null ? item.status : <StatusChip status={spec.status} />}
                </td>
                <td className="num px-3 py-2">{formatDate(item.effective_from_date)}</td>
                <td className="num px-3 py-2">{formatDate(item.effective_to_date)}</td>
                <td className="num px-3 py-2 text-end">
                  {formatNumber(item.entry_count, { kind: "count" })}
                </td>
                <td className="px-3 py-2">{item.methodology_label}</td>
                <td className="num px-3 py-2">{formatTimestamp(item.published_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface StudyPaneProps {
  readonly version: SspBookVersion;
  readonly editable: boolean;
  readonly attachments: readonly Attachment[] | undefined;
  readonly invalidates: readonly QueryKey[];
}

/** SCREENS §11.4 Study panel: the `SSP_STUDY` attachments with SHA-256, upload and removal. */
function StudyPane({ version, editable, attachments, invalidates }: StudyPaneProps) {
  const toast = useToast();
  const keys = useCommandKeys();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [voiding, setVoiding] = useState<Attachment | null>(null);
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  const [voidPending, setVoidPending] = useState(false);
  const formId = useId();

  const upload = async (file: File) => {
    setUploading(true);
    setProblem(null);
    try {
      const stored = await uploadFile(keys, STUDY_PURPOSE, file);
      const attached = await postCommand<Attachment>(keys, ATTACHMENTS_PATH, {
        file_object_id: stored.id,
        subject_type: STUDY_SUBJECT_TYPE,
        subject_id: version.id,
        description: t("policies.sspVersion.study.description", { name: file.name }),
      });
      if (!attached.ok) {
        setProblem(commandProblemTitle(attached.problem));
        return;
      }
      await invalidateAll(queryClient, invalidates);
      toast.show({
        tone: "positive",
        message: t("policies.sspVersion.study.attached", { name: file.name }),
      });
    } catch (error) {
      // Without an answer the same file chosen again is sent under the same keys (DG-FE-05).
      setProblem(
        error instanceof ApiProblem ? commandProblemTitle(error) : t("common.command.noAnswer"),
      );
    } finally {
      setUploading(false);
    }
  };

  const submitVoid = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTried(true);
    if (voiding === null || reason.trim() === "" || voidPending) {
      return;
    }
    setVoidPending(true);
    const outcome = await postCommand<Attachment>(keys, `${ATTACHMENTS_PATH}/${voiding.id}/void`, {
      reason: reason.trim(),
    }).catch(() => null);
    setVoidPending(false);
    if (outcome === null) {
      // No answer: the dialog stays, and the next press sends the same key (DG-FE-05).
      setProblem(t("common.command.noAnswer"));
      return;
    }
    if (!outcome.ok) {
      setProblem(commandProblemTitle(outcome.problem));
      setVoiding(null);
      return;
    }
    await invalidateAll(queryClient, invalidates);
    toast.show({
      tone: "positive",
      message: t("policies.sspVersion.study.removed", {
        name: voiding.original_filename ?? voiding.sha256.slice(0, 12),
      }),
    });
    setVoiding(null);
    setReason("");
    setTried(false);
  };

  let body: ReactNode;
  if (attachments === undefined) {
    body = <Skeleton region={t("policies.sspVersion.study.title")} shape="rows" count={2} />;
  } else if (attachments.length === 0) {
    body = (
      <EmptyState
        title={t("policies.sspVersion.study.empty.title")}
        description={t("policies.sspVersion.studyRequired")}
        headingLevel={3}
      />
    );
  } else {
    body = (
      <table className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-title-sm text-fg-1">
          {t("policies.sspVersion.study.title")}
        </caption>
        <thead>
          <tr className="border-b border-default bg-subtle">
            <th scope="col" className="px-3 py-2 text-start font-medium text-fg-2">
              {t("policies.sspVersion.study.column.file")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium text-fg-2">
              {t("policies.sspVersion.study.column.sha")}
            </th>
            <th scope="col" className="px-3 py-2 text-start font-medium text-fg-2">
              {t("policies.sspVersion.study.column.uploaded")}
            </th>
            {editable ? (
              <th scope="col" className="px-3 py-2 text-end font-medium text-fg-2">
                <span className="sr-only">{t("policies.sspVersion.study.column.actions")}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {attachments.map((item) => {
            const name = item.original_filename ?? item.sha256.slice(0, 12);
            return (
              <tr key={item.id} className="border-b border-hairline">
                <th scope="row" className="px-3 py-2 text-start font-normal text-fg-1">
                  {name}
                </th>
                <td className="px-3 py-2">
                  <span className="break-all font-mono text-mono-sm">{item.sha256}</span>
                </td>
                <td className="num px-3 py-2">{formatTimestamp(item.created_at)}</td>
                {editable ? (
                  <td className="px-3 py-2 text-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={t("policies.sspVersion.study.removeNamed", { name })}
                      onClick={() => setVoiding(item)}
                    >
                      {t("policies.sspVersion.study.remove")}
                    </Button>
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <div className="flex flex-col gap-3 pt-3">
      {problem === null ? null : <Banner tone="negative" announce="live" title={problem} />}
      {editable ? (
        <div>
          <Button
            variant="secondary"
            size="sm"
            loading={uploading}
            onClick={() => input.current?.click()}
          >
            {t("policies.sspVersion.study.upload")}
          </Button>
          <input
            ref={input}
            type="file"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file !== undefined) {
                void upload(file);
              }
            }}
          />
        </div>
      ) : null}
      {body}
      {voiding === null ? null : (
        <Modal
          open
          variant="form"
          title={t("policies.sspVersion.study.removeTitle", {
            name: voiding.original_filename ?? voiding.sha256.slice(0, 12),
          })}
          description={t("policies.sspVersion.study.removeDescription")}
          primaryAction={{ label: t("policies.sspVersion.study.remove"), form: formId }}
          submitting={voidPending}
          onClose={() => {
            setVoiding(null);
            setReason("");
            setTried(false);
          }}
        >
          <form id={formId} noValidate onSubmit={(event) => void submitVoid(event)}>
            <ReasonField
              label={t("policies.sspVersion.study.reason")}
              value={reason}
              onChange={setReason}
              minimum={1}
              showError={tried}
            />
          </form>
        </Modal>
      )}
    </div>
  );
}
