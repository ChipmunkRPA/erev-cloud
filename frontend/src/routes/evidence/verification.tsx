// SF-09:verification Audit chain verification (SCREENS_B §6.4; §0.4 E-98; §5.6.5 RPT-44; SCREENS §0.4
// RT-38; §0.6 SCR-PERM-01; §0.7 SCR-ST-07; DESIGN_SYSTEM DS-CMP-06, DS-CMP-19, DS-CMP-29, DS-FMT-17,
// DS-FMT-20, DS-FMT-23; 04 API-R-10, T-PLT-23; API-R-12 `GET /files/{id}/content`; REQ-PLT-020; CTL-039;
// BUILD_SPEC RPS-21). One verification run: the record header with the E-98 chip, "Download digest"
// (the digest file of a run that passed), the trigger, the start and finish instants with seconds and
// the sequence range, then the key figures Events checked, First failure and Last chain value; on a
// failed run the negative banner and the table "Failure detail"; and the static table "Recent
// verifications" of the ten that finished last, with "Open register" (RPT-44). The run is read by its
// id (`GET /audit-events/verifications/{id}`, 04 rev 1.154; SCREENS_B rev 1.57); an id the workspace
// does not hold is SCR-ST-07.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { DownloadSimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { KpiStrip } from "../../components/record/KpiStrip";
import { type Crumb, RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { ApiProblem, isRefused } from "../../lib/api/problems";
import {
  AUDIT_LOG_ROUTE,
  AUDIT_READ_PERMISSION,
  auditEventRoute,
  digestHref,
  fetchRecentVerifications,
  fetchVerification,
  recentVerificationsKey,
  VERIFICATION_REPORT_CODE,
  verificationKey,
  verificationRoute,
} from "../../lib/api/queries/audit";
import { useMe } from "../../lib/api/queries/me";
import { REPORT_ROUTE, REPORT_RUN_PERMISSION, REPORTS_ROUTE } from "../../lib/api/queries/reports";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { hashPrefix } from "../reports/viewer/RunStamp";
import { useBuiltPaths } from "../settings/index";
import { AuditAccessLimited, failureTitle, recordedText, resultWord, triggerLabel } from "./chain";

function count(value: number): string {
  return formatNumber(value, { kind: "count" });
}

/** When the run was recorded: masked in captures (SCR-TID-05). */
function Instant({ value }: { readonly value: string }) {
  return (
    <time dateTime={value} data-volatile="" className="num">
      {formatTimestamp(value, { seconds: true })}
    </time>
  );
}

export function VerificationPage() {
  const { verificationId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={t("evidence.verification.title")} shape="rows" count={6} />;
  }
  if (!access.holdsAnywhere(AUDIT_READ_PERMISSION)) {
    return (
      <div data-testid="SF-09-page" className="px-[var(--gutter)]">
        <AuditAccessLimited />
      </div>
    );
  }
  return <VerificationRecord key={verificationId} verificationId={verificationId} />;
}

interface VerificationRecordProps {
  readonly verificationId: string;
}

function VerificationRecord({ verificationId }: VerificationRecordProps) {
  const access = useAccess();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const verification = useQuery({
    queryKey: verificationKey(verificationId),
    queryFn: () => fetchVerification(verificationId),
    // A refusal is not repaired by asking again (SCREENS §0.6 SCR-PERM-02).
    retry: (count, error) => !isRefused(error) && count < 1,
  });
  const reports = access.holdsAnywhere(REPORT_RUN_PERMISSION);
  const breadcrumb: Crumb[] = [
    ...(reports && built.has(REPORTS_ROUTE)
      ? [{ label: t("reports.report.breadcrumb"), to: REPORTS_ROUTE }]
      : []),
    { label: t("evidence.auditLog.title"), to: AUDIT_LOG_ROUTE },
  ];

  if (isRefused(verification.error)) {
    // SCREENS_B §6.4: the state of a member without access, not an error with "Retry".
    return (
      <div data-testid="SF-09-page" className="px-[var(--gutter)]">
        <AuditAccessLimited allEntities />
      </div>
    );
  }
  if (verification.isError) {
    return (
      <div data-testid="SF-09-page" className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("evidence.verification.loadError")}
          actions={
            <Button variant="link" onClick={() => void verification.refetch()}>
              {t("evidence.auditLog.retry")}
            </Button>
          }
        >
          <p>
            {verification.error instanceof ApiProblem
              ? verification.error.title
              : verification.error.message}
          </p>
        </Banner>
      </div>
    );
  }
  if (verification.data === undefined) {
    return (
      <div data-testid="SF-09-page" className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Skeleton region={t("evidence.verification.title")} shape="rows" count={6} />
      </div>
    );
  }
  if (verification.data === null) {
    // SCR-ST-07: the list holds no verification with this id.
    return (
      <div data-testid="SF-09-page" className="px-[var(--gutter)]">
        <EmptyState
          title={t("evidence.verification.notFound.title")}
          description={t("evidence.verification.notFound.description")}
          action={{
            label: t("evidence.verification.notFound.action"),
            onAction: () => void navigate(AUDIT_LOG_ROUTE),
          }}
        />
      </div>
    );
  }

  const record = verification.data;
  const failed = record.result === "FAIL";
  const register =
    reports && built.has(REPORT_ROUTE) ? `/reports/${VERIFICATION_REPORT_CODE}` : null;
  return (
    <div data-testid="SF-09-page" className="flex flex-col gap-4">
      <RecordHeader
        title={t("evidence.verification.title")}
        breadcrumb={breadcrumb}
        chips={<StatusChip status={resultWord(record.result)} />}
        actions={
          record.digest_file_id === null ? undefined : (
            <a
              href={digestHref(record.digest_file_id)}
              download
              className="inline-flex h-[var(--control-h)] shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md bg-accent-solid px-3 text-body-sm font-medium text-on-accent hover:bg-accent-solid-hover active:bg-accent-solid-active"
            >
              <DownloadSimple aria-hidden="true" className="shrink-0" />
              {t("evidence.verification.downloadDigest")}
            </a>
          )
        }
        meta={[
          { label: t("evidence.verification.meta.trigger"), value: triggerLabel(record.trigger) },
          {
            label: t("evidence.verification.meta.started"),
            value: <Instant value={record.started_at} />,
          },
          {
            label: t("evidence.verification.meta.finished"),
            value: <Instant value={record.finished_at} />,
          },
          {
            label: t("evidence.verification.meta.sequences"),
            value: (
              <span className="num">
                {t("evidence.verification.sequences", {
                  from: count(record.from_chain_seq),
                  to: count(record.to_chain_seq),
                })}
              </span>
            ),
          },
        ]}
        banner={
          failed ? (
            <div data-testid="SF-09-banner-verification-failed">
              {/* DS-CMP-29: the banner is present on load, so it is a static element with a heading. */}
              <Banner
                tone="negative"
                announce="static"
                title={failureTitle(record)}
                actions={
                  // SCREENS_B §6.4 rev 1.45: the first failing event, by its chain sequence.
                  record.first_failure_seq === null ? undefined : (
                    <Link
                      to={auditEventRoute(record.first_failure_seq)}
                      className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
                    >
                      {t("evidence.verification.openEvent", {
                        event: count(record.first_failure_seq),
                      })}
                    </Link>
                  )
                }
              >
                {t("evidence.auditLog.chain.failedBody")}
              </Banner>
            </div>
          ) : undefined
        }
        kpis={
          <KpiStrip
            heading={t("evidence.verification.kpi.heading")}
            region
            testId="SF-09-kpi-strip"
            kpis={[
              {
                id: "events",
                label: t("evidence.verification.kpi.events"),
                value: String(record.events_checked),
                currency: "",
                kind: "count",
              },
              {
                id: "failure",
                label: t("evidence.verification.kpi.firstFailure"),
                value: record.first_failure_seq === null ? null : String(record.first_failure_seq),
                currency: "",
                kind: "count",
              },
              {
                id: "chain",
                label: t("evidence.verification.kpi.lastChainValue"),
                value:
                  record.digest_last_hmac === null ? null : hashPrefix(record.digest_last_hmac),
                currency: "",
                kind: "text",
              },
            ]}
          />
        }
      />
      <div className="flex flex-col gap-6 px-[var(--gutter)] pb-[var(--panel-pad)]">
        {failed && record.failure_detail !== null ? (
          <FailureDetail detail={record.failure_detail} />
        ) : null}
        <RecentVerifications currentId={record.id} register={register} />
      </div>
    </div>
  );
}

const TABLE = "w-full border-separate border-spacing-0 rounded-md border border-default bg-surface";
const HEADER = "px-3 py-2 text-start text-body-sm font-medium text-fg-2";
const CELL = "border-t border-hairline px-3 py-2 text-body-sm text-fg-1";

/** SCREENS_B §6.4 "Failure detail": the keys and values of `failure_detail`. */
function FailureDetail({ detail }: { readonly detail: Readonly<Record<string, unknown>> }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("evidence.verification.failureDetail.title")}
      </h2>
      <table aria-labelledby={headingId} className={TABLE}>
        <thead className="bg-subtle">
          <tr>
            <th scope="col" className={HEADER}>
              {t("evidence.verification.failureDetail.key")}
            </th>
            <th scope="col" className={HEADER}>
              {t("evidence.verification.failureDetail.value")}
            </th>
          </tr>
        </thead>
        <tbody>
          {Object.keys(detail)
            .sort()
            .map((key) => (
              <tr key={key}>
                <th
                  scope="row"
                  className={`${CELL} text-start font-mono text-mono-sm font-normal text-fg-2`}
                >
                  {key}
                </th>
                <td className={`${CELL} break-all font-mono text-mono-sm`}>
                  {recordedText(detail[key]) ?? <NoValue />}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </section>
  );
}

interface RecentVerificationsProps {
  readonly currentId: string;
  /** RPT-44, where the viewer may run it. */
  readonly register: string | null;
}

/** SCREENS_B §6.4 "Recent verifications": the ten that finished last. */
function RecentVerifications({ currentId, register }: RecentVerificationsProps) {
  const headingId = useId();
  const recent = useQuery({
    queryKey: recentVerificationsKey(),
    queryFn: fetchRecentVerifications,
  });
  let content: ReactNode;
  if (recent.isError) {
    content = (
      <Banner
        tone="negative"
        headingLevel={3}
        title={t("evidence.verification.recent.loadError")}
        actions={
          <Button variant="link" onClick={() => void recent.refetch()}>
            {t("evidence.auditLog.retry")}
          </Button>
        }
      />
    );
  } else if (recent.data === undefined) {
    content = <Skeleton region={t("evidence.verification.recent.title")} shape="rows" count={3} />;
  } else {
    content = (
      <table data-testid="SF-09-grid-verifications" aria-labelledby={headingId} className={TABLE}>
        <thead className="bg-subtle">
          <tr>
            <th scope="col" className={HEADER}>
              {t("evidence.verification.recent.column.finished")}
            </th>
            <th scope="col" className={HEADER}>
              {t("evidence.verification.recent.column.trigger")}
            </th>
            <th scope="col" className={HEADER}>
              {t("evidence.verification.recent.column.result")}
            </th>
            <th scope="col" className={`${HEADER} text-end`}>
              {t("evidence.verification.recent.column.events")}
            </th>
            <th scope="col" className={`${HEADER} text-end`}>
              {t("evidence.verification.recent.column.firstFailure")}
            </th>
          </tr>
        </thead>
        <tbody>
          {recent.data.map((item) => (
            <tr key={item.id} aria-current={item.id === currentId ? "true" : undefined}>
              <td className={CELL} data-volatile="">
                {item.id === currentId ? (
                  <time dateTime={item.finished_at} className="num font-medium">
                    {formatTimestamp(item.finished_at)}
                  </time>
                ) : (
                  <Link to={verificationRoute(item.id)} className="text-accent-fg hover:underline">
                    <time dateTime={item.finished_at} className="num">
                      {formatTimestamp(item.finished_at)}
                    </time>
                  </Link>
                )}
              </td>
              <td className={CELL}>{triggerLabel(item.trigger)}</td>
              <td className={CELL}>
                <StatusChip status={resultWord(item.result)} />
              </td>
              <td className={`${CELL} num text-end`}>{count(item.events_checked)}</td>
              <td className={`${CELL} num text-end`}>
                {item.first_failure_seq === null ? <NoValue /> : count(item.first_failure_seq)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={headingId} className="text-title-sm text-fg-1">
          {t("evidence.verification.recent.title")}
        </h2>
        <span className="flex-1" />
        {register === null ? null : (
          <Link
            to={register}
            className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
          >
            {t("evidence.verification.recent.register")}
          </Link>
        )}
      </div>
      {content}
    </section>
  );
}
