// SF-06:run-batches Journal run: batches and acknowledgements (SCREENS_B §3.4; §0.3 SB-R-08; §0.4 E-34;
// SCREENS RT-105; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-FMT-16, DS-FMT-17, DS-FMT-23,
// DS-I18N-07; 04 API-R-38 `GET /journal-runs/{id}/batches`, `GET /journal-batches/{id}`, `GET …/download`,
// `POST …/acknowledge`, `POST …/retry`, API-S-PostingAck; REQ-JE-011 to REQ-JE-016; BUILD_SPEC CLO-26). Each
// batch chunk with its state, external id `erev:<tenant>:<run no>:<batch>:<chunk>` (T-SL-07), adapter and
// acknowledgements; "Record ERP reference" for exported chunks, "Retry export" for failed chunks, and
// the batch drawer with the acknowledgements table (`drawer=batch&row=<batch id>`). Rev 1.71 (04 §16.7
// rev 1.159; item JRN-FAILED-EXITS-UI-1): "Hand over" sends a failed chunk of an ERP adapter out as its
// file for manual posting — `POST …/hand-over`, a job the frame follows — after which the chunk is
// `exported` and waits for its ERP reference as a CSV chunk does; "Download" fetches before it saves.
// Rev 1.77 (item JRN-RETRY-FOLLOW-1): the job of "Retry export" is followed by the frame too, which
// says what became of the batch; a refused download is said in the frame's banner; and a command that
// gets no answer says so in every dialog.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { sandboxTenantName, useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { Field } from "../../components/form/Field";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  batchDownloadHref,
  EVERY_JOURNAL_BATCH,
  EVERY_JOURNAL_RUN,
  fetchJournalBatch,
  fetchRunBatchesPage,
  JOURNAL_BATCHES_PATH,
  JOURNAL_EXPORT_PERMISSION,
  type JournalBatch,
  journalBatchKey,
  journalRunBatchesKey,
  type PostingAck,
  REPORT_EXPORT_PERMISSION,
  runRoute,
} from "../../lib/api/queries/journal-runs";
import { formatDate, formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { TextField } from "../contracts/drawers/common";
import {
  adapterText,
  batchLabel,
  failedInLedger,
  MoneyCell,
  Mono,
  RetryBanner,
  RunFrame,
  type RunContext,
} from "./run";

/** Columns hidden by the default view: none at 1440 px (§3.4 wireframe). */
export const BATCH_HIDDEN: readonly string[] = [];

/** The GL document of the latest acknowledgement, else null (§3.4 "GL document"). */
export function latestDocument(batch: Pick<JournalBatch, "acknowledgements">): string | null {
  const latest = [...batch.acknowledgements]
    .filter((ack) => ack.gl_document_id !== null)
    .sort((left, right) => (left.received_at < right.received_at ? -1 : 1))
    .at(-1);
  return latest?.gl_document_id ?? null;
}

/**
 * The E-34 chip of a batch. A batch that was handed over is `exported` like a CSV export and is not told
 * apart here: API-S-JournalBatch does not say so yet. The instant of the hand-over joins the schema with
 * lane F-CLO-A's next item, and its caption belongs on this chip (§3.4 rev 1.71).
 */
function BatchState({ batch }: { readonly batch: JournalBatch }) {
  const chip = chipFor("E-34", batch.state);
  return chip === null ? null : <StatusChip status={chip.status} />;
}

interface BatchColumnSources {
  readonly runId: string;
  readonly ctxSearch: string;
  readonly canExport: boolean;
  readonly canDownload: boolean;
  readonly sandbox: boolean;
  /**
   * The frame follows a job of the run that has not ended — a cancel, a hand-over, a retry or an
   * export: the commands of a failed batch wait for its end.
   */
  readonly jobUnderWay: boolean;
  readonly openDrawer: (batch: JournalBatch) => void;
  readonly download: (batch: JournalBatch) => void;
  readonly record: (batch: JournalBatch) => void;
  readonly retry: (batch: JournalBatch) => void;
  readonly handOver: (batch: JournalBatch) => void;
}

function batchColumns({
  runId,
  ctxSearch,
  canExport,
  canDownload,
  sandbox,
  jobUnderWay,
  openDrawer,
  download,
  record,
  retry,
  handOver,
}: BatchColumnSources): readonly GridColumn<JournalBatch>[] {
  const join = ctxSearch === "" ? "?" : `${ctxSearch}&`;
  return [
    {
      id: "batch",
      header: t("journals.batches.column.batch"),
      kind: "text",
      value: batchLabel,
      render: (batch) => (
        <Button variant="link" tabIndex={-1} onClick={() => openDrawer(batch)}>
          <span className="num">{batchLabel(batch)}</span>
        </Button>
      ),
      width: 96,
    },
    {
      id: "currency",
      header: t("journals.batches.column.currency"),
      kind: "text",
      value: (batch) => batch.txn_currency,
      render: (batch) => <Mono>{batch.txn_currency}</Mono>,
      width: 104,
    },
    {
      id: "state",
      header: t("journals.batches.column.state"),
      kind: "status",
      value: (batch) => batch.state,
      render: (batch) => <BatchState batch={batch} />,
      width: 136,
    },
    {
      id: "line_count",
      header: t("journals.batches.column.lines"),
      kind: "number",
      value: (batch) => String(batch.line_count),
      render: (batch) => (
        <Link
          to={`${runRoute(runId, "lines")}${join}f.batch=is:${batch.id}`}
          tabIndex={-1}
          className="num text-accent-fg hover:underline"
        >
          {formatNumber(batch.line_count, { kind: "count" })}
        </Link>
      ),
      width: 96,
    },
    {
      id: "debit",
      header: t("journals.batches.column.debit"),
      kind: "money",
      value: (batch) => batch.total_debit_txn.amount,
      currency: (batch) => batch.txn_currency,
      render: (batch) => (
        <MoneyCell value={batch.total_debit_txn.amount} currency={batch.total_debit_txn.currency} />
      ),
      width: 160,
    },
    {
      id: "credit",
      header: t("journals.batches.column.credit"),
      kind: "money",
      value: (batch) => batch.total_credit_txn.amount,
      currency: (batch) => batch.txn_currency,
      render: (batch) => (
        <MoneyCell
          value={batch.total_credit_txn.amount}
          currency={batch.total_credit_txn.currency}
        />
      ),
      width: 160,
    },
    {
      id: "external_id",
      header: t("journals.batches.column.externalId"),
      kind: "text",
      value: (batch) => batch.external_id,
      // DS-FMT-23: external ids are never truncated; DS-I18N-07: isolated LTR.
      render: (batch) => (
        <bdi dir="ltr" className="whitespace-nowrap font-mono text-mono-sm text-fg-1">
          {batch.external_id}
        </bdi>
      ),
      width: 320,
    },
    {
      id: "adapter",
      header: t("journals.batches.column.adapter"),
      kind: "text",
      value: (batch) => adapterText(batch.adapter),
      width: 136,
    },
    {
      id: "exported_at",
      header: t("journals.batches.column.exported"),
      kind: "timestamp",
      value: (batch) => batch.exported_at,
      width: 192,
    },
    {
      id: "acknowledged_at",
      header: t("journals.batches.column.acknowledged"),
      kind: "timestamp",
      value: (batch) => batch.acknowledged_at,
      width: 192,
    },
    {
      id: "gl_document",
      header: t("journals.batches.column.glDocument"),
      kind: "text",
      value: latestDocument,
      render: (batch) => {
        const document = latestDocument(batch);
        return document === null ? <NoValue /> : <Mono>{document}</Mono>;
      },
      width: 136,
    },
    {
      id: "attempt_count",
      header: t("journals.batches.column.attempts"),
      kind: "number",
      value: (batch) => String(batch.attempt_count),
      // Holds the header without clipping (CLO-26; DS-AP-10).
      width: 112,
    },
    {
      id: "last_error",
      header: t("journals.batches.column.lastError"),
      kind: "text",
      value: (batch) => batch.last_error,
      render: (batch) =>
        batch.last_error === null ? (
          <NoValue />
        ) : (
          <span className="truncate" title={batch.last_error}>
            {batch.last_error}
          </span>
        ),
      width: 240,
    },
    {
      id: "actions",
      header: t("journals.batches.column.actions"),
      kind: "text",
      value: () => null,
      render: (batch) => (
        <span className="flex items-center gap-2">
          {canDownload ? (
            <a
              href={batchDownloadHref(batch.id)}
              download
              tabIndex={-1}
              aria-label={t("journals.batches.action.downloadName", { batch: batchLabel(batch) })}
              className="text-body-sm text-accent-fg hover:underline"
              // The link's plain press is fetched and then saved, so that a refused download is said
              // (PRD ERR-79); a press with a modifier key stays the browser's, with the address.
              onClick={(event) => {
                const modified = event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
                if (event.button !== 0 || modified) {
                  return;
                }
                event.preventDefault();
                download(batch);
              }}
            >
              {t("journals.batches.action.download")}
            </a>
          ) : null}
          {/* Any adapter: a batch handed over waits for its reference as a CSV batch does (BR-JE-03). */}
          {canExport && batch.state === "exported" ? (
            <Button
              variant="link"
              tabIndex={-1}
              aria-label={t("journals.batches.action.recordName", { batch: batchLabel(batch) })}
              onClick={() => record(batch)}
            >
              {t("journals.batches.action.record")}
            </Button>
          ) : null}
          {canExport && !jobUnderWay && batch.state === "failed" ? (
            <Button
              variant="link"
              tabIndex={-1}
              disabledReason={sandbox ? t("journals.sandboxReason") : undefined}
              aria-label={t("journals.batches.action.retryName", { batch: batchLabel(batch) })}
              onClick={() => retry(batch)}
            >
              {t("journals.batches.action.retry")}
            </Button>
          ) : null}
          {canExport && !jobUnderWay && failedInLedger(batch) ? (
            <Button
              variant="link"
              tabIndex={-1}
              disabledReason={sandbox ? t("journals.sandboxReason") : undefined}
              aria-label={t("journals.batches.action.handOverName", { batch: batchLabel(batch) })}
              onClick={() => handOver(batch)}
            >
              {t("journals.batches.action.handOver")}
            </Button>
          ) : null}
        </span>
      ),
      width: 320,
    },
  ];
}

export function JournalRunBatchesPage() {
  return <RunFrame tab="batches">{(context) => <BatchesTab {...context} />}</RunFrame>;
}

function BatchesTab({ run, ctxSearch, jobUnderWay, followJob, download }: RunContext) {
  const location = useLocation();
  const navigate = useNavigate();
  const sandbox = sandboxTenantName(useShellSession()) !== null;
  // SCREENS SCR-PERM-02 (a): the batches of a run are records of the run's legal entity (DG-FE-16).
  const access = useAccess();
  const canExport = access.holds(JOURNAL_EXPORT_PERMISSION, run.entity);
  const canDownload = canExport || access.holds(REPORT_EXPORT_PERMISSION, run.entity);
  const params = new URLSearchParams(location.search);
  const drawerBatchId = params.get("drawer") === "batch" ? params.get("row") : null;
  const [recording, setRecording] = useState<JournalBatch | null>(null);
  const [retrying, setRetrying] = useState<JournalBatch | null>(null);
  const [handingOver, setHandingOver] = useState<JournalBatch | null>(null);

  // Search updates keep raw values, so `f.*` operator colons stay unencoded (SCR-URL-20).
  const setDrawer = (batchId: string | null) => {
    const changes =
      batchId === null ? { drawer: null, row: null } : { drawer: "batch", row: batchId };
    void navigate({ search: withParams(location.search, changes) }, { replace: true });
  };
  const opener = useRef(setDrawer);
  useEffect(() => {
    opener.current = setDrawer;
  });

  const source: GridSource<JournalBatch> = {
    queryKey: journalRunBatchesKey(run.id),
    fetchPage: (cursor) => fetchRunBatchesPage(run.id, cursor),
  };
  const columns = useMemo(
    () =>
      batchColumns({
        runId: run.id,
        ctxSearch,
        canExport,
        canDownload,
        sandbox,
        jobUnderWay,
        openDrawer: (batch) => opener.current(batch.id),
        download,
        record: setRecording,
        retry: setRetrying,
        handOver: setHandingOver,
      }),
    [run.id, ctxSearch, canExport, canDownload, sandbox, jobUnderWay, download],
  );
  const defaultColumns = useMemo(
    (): GridColumnState => initialColumnState(columns, BATCH_HIDDEN),
    [columns],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);

  return (
    <div className="flex min-h-80 flex-col">
      <DataGrid<JournalBatch>
        name="batches"
        title={t("journals.batches.title")}
        errorTitle={t("journals.batches.loadError")}
        countLabel={(count, formatted) => t("journals.batches.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(batch) => batch.id}
        rowLabel={(batch) => t("journals.batches.rowLabel", { batch: batchLabel(batch) })}
        testIdPrefix="SF-06"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        emptyState={
          <EmptyState
            title={t("journals.batches.empty")}
            description={t("journals.batches.emptyDescription")}
            headingLevel={3}
          />
        }
      />
      {drawerBatchId === null ? null : (
        <BatchDrawer batchId={drawerBatchId} onClose={() => setDrawer(null)} />
      )}
      {recording === null ? null : (
        <RecordReferenceDialog batch={recording} onClose={() => setRecording(null)} />
      )}
      {retrying === null ? null : (
        <RetryDialog
          batch={retrying}
          onAccepted={(jobId) =>
            followJob({
              jobId,
              mode: "RETRY",
              batch: batchLabel(retrying),
              batchId: retrying.id,
            })
          }
          onClose={() => setRetrying(null)}
        />
      )}
      {handingOver === null ? null : (
        <HandOverDialog
          batch={handingOver}
          onAccepted={(jobId) =>
            followJob({ jobId, mode: "HAND_OVER", batch: batchLabel(handingOver) })
          }
          onClose={() => setHandingOver(null)}
        />
      )}
    </div>
  );
}

function Definition({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(8rem,12rem)_1fr] gap-3 border-b border-hairline py-1.5">
      <dt className="text-body-sm text-fg-3">{label}</dt>
      <dd className="text-body-sm text-fg-1">{children}</dd>
    </div>
  );
}

const CELL = "px-2 py-1.5 text-body-sm";

/** §3.4 batch drawer (DS-CMP-09 informational): attempts, last error and the acknowledgements table. */
function BatchDrawer({
  batchId,
  onClose,
}: {
  readonly batchId: string;
  readonly onClose: () => void;
}) {
  const batch = useQuery({
    queryKey: journalBatchKey(batchId),
    queryFn: () => fetchJournalBatch(batchId),
  });
  const data = batch.data;
  return (
    <Drawer
      open
      variant="docked"
      wide
      title={data === undefined ? t("journals.batches.drawer.loading") : batchLabel(data)}
      initialFocus="title"
      onClose={onClose}
    >
      <div data-testid="SF-06-drawer-batch" className="flex flex-col gap-4">
        {batch.error !== null ? (
          <RetryBanner
            title={t("journals.batches.drawer.loadError")}
            problem={batch.error}
            onRetry={() => void batch.refetch()}
          />
        ) : data === undefined ? (
          <Skeleton region={t("journals.batches.drawer.region")} shape="rows" count={4} />
        ) : (
          <>
            <dl>
              <Definition label={t("journals.batches.column.externalId")}>
                <bdi dir="ltr" className="font-mono text-mono-sm">
                  {data.external_id}
                </bdi>
              </Definition>
              <Definition label={t("journals.batches.column.adapter")}>
                {adapterText(data.adapter)}
              </Definition>
              <Definition label={t("journals.batches.column.exported")}>
                {data.exported_at === null ? NO_VALUE : formatTimestamp(data.exported_at)}
              </Definition>
              <Definition label={t("journals.batches.column.attempts")}>
                {formatNumber(data.attempt_count, { kind: "count" })}
              </Definition>
              <Definition label={t("journals.batches.column.lastError")}>
                {data.last_error ?? NO_VALUE}
              </Definition>
            </dl>
            <Acknowledgements acks={data.acknowledgements} />
          </>
        )}
      </div>
    </Drawer>
  );
}

function Acknowledgements({ acks }: { readonly acks: readonly PostingAck[] }) {
  if (acks.length === 0) {
    return <p className="text-body-sm text-fg-3">{t("journals.batches.acks.empty")}</p>;
  }
  const headers = [
    "kind",
    "document",
    "posted",
    "message",
    "sha",
    "received",
    "recordedBy",
  ] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <caption className="py-1 text-start text-title-sm text-fg-1">
          {t("journals.batches.acks.caption")}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            {headers.map((id) => (
              <th key={id} scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
                {t(`journals.batches.acks.column.${id}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {acks.map((ack) => (
            <tr key={ack.id} className="border-b border-hairline last:border-b-0">
              <td className={CELL}>{t(`journals.batches.acks.kind.${ack.ack_kind}`)}</td>
              <td className={CELL}>
                {ack.gl_document_id === null ? <NoValue /> : <Mono>{ack.gl_document_id}</Mono>}
              </td>
              <td className={CELL}>
                {ack.gl_posted_date === null ? NO_VALUE : formatDate(ack.gl_posted_date)}
              </td>
              <td className={CELL}>{ack.message ?? NO_VALUE}</td>
              <td className={CELL}>
                {ack.response_sha256 === null ? (
                  <NoValue />
                ) : (
                  <Mono>{ack.response_sha256.slice(0, 12)}</Mono>
                )}
              </td>
              <td className={CELL}>{formatTimestamp(ack.received_at)}</td>
              <td className={CELL}>
                {ack.recorded_by.kind === "USER"
                  ? ack.recorded_by.display_name
                  : t("journals.batches.acks.system")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** §3.4 "Record ERP reference" (BR-JE-03): `POST /journal-batches/{id}/acknowledge`. */
function RecordReferenceDialog({
  batch,
  onClose,
}: {
  readonly batch: JournalBatch;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const [reference, setReference] = useState("");
  const [postedText, setPostedText] = useState("");
  const [postedDate, setPostedDate] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${JOURNAL_BATCHES_PATH}/${batch.id}/acknowledge`,
    invalidates: [EVERY_JOURNAL_RUN, EVERY_JOURNAL_BATCH],
  });
  const missing = reference.trim() === "";
  const submit = async () => {
    setAttempted(true);
    if (missing) {
      return;
    }
    const outcome = await command.submit({
      gl_document_id: reference.trim(),
      gl_posted_date: postedDate,
      message: message.trim() === "" ? null : message.trim(),
    });
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({
        tone: "positive",
        message: t("journals.batches.record.done", {
          batch: batchLabel(batch),
          reference: reference.trim(),
        }),
      });
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("journals.batches.record.title", { batch: batchLabel(batch) })}
      primaryAction={{ label: t("journals.batches.record.confirm"), form: formId }}
      submitting={command.pending}
      onClose={onClose}
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
        <RefusalBanner problem={command.problem} />
        <TextField
          name="journal-batch-reference"
          label={t("journals.batches.record.reference")}
          required
          value={reference}
          onChange={setReference}
          error={attempted && missing ? t("journals.batches.record.referenceMissing") : null}
        />
        <Field
          name="journal-batch-posted"
          label={t("journals.batches.record.posted")}
          optional
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={postedText}
              onChange={setPostedText}
              onValue={setPostedDate}
            />
          )}
        </Field>
        <TextField
          name="journal-batch-message"
          label={t("journals.batches.record.message")}
          optional
          multiline
          value={message}
          onChange={setMessage}
        />
      </form>
    </Modal>
  );
}

/**
 * §3.4 "Retry export": `POST /journal-batches/{id}/retry` (202). The dialog closes on the accepted
 * command and the frame follows the job (rev 1.77): the job ends SUCCEEDED whether or not it sent the
 * batch, and until this revision nothing read the run again after it. A refusal of the command itself
 * stays here, as sent.
 */
function RetryDialog({
  batch,
  onAccepted,
  onClose,
}: {
  readonly batch: JournalBatch;
  readonly onAccepted: (jobId: string) => void;
  readonly onClose: () => void;
}) {
  const noAnswer = useNoAnswer();
  const command = useCommand({
    method: "POST",
    path: `${JOURNAL_BATCHES_PATH}/${batch.id}/retry`,
    invalidates: [EVERY_JOURNAL_RUN, EVERY_JOURNAL_BATCH],
  });
  const submit = async () => {
    const outcome = await command.submit();
    if (outcome.kind === "accepted") {
      onAccepted(outcome.jobId);
    }
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("journals.batches.retry.title", { batch: batchLabel(batch) })}
      description={t("journals.batches.retry.consequence")}
      primaryAction={{ label: t("journals.batches.action.retry"), onAction: () => void submit() }}
      submitting={command.pending}
      onClose={onClose}
    >
      <RefusalBanner problem={command.problem} />
    </Modal>
  );
}

/**
 * §3.4 "Hand over" (rev 1.71): `POST /journal-batches/{id}/hand-over` (202; 04 §16.7 rev 1.159). A job
 * asks the ledger whether it holds the batch and, if it does not, exports the batch as its file; the
 * dialog closes on the accepted command and the frame follows that job. A refusal of the command itself
 * stays here, as sent.
 */
function HandOverDialog({
  batch,
  onAccepted,
  onClose,
}: {
  readonly batch: JournalBatch;
  readonly onAccepted: (jobId: string) => void;
  readonly onClose: () => void;
}) {
  const noAnswer = useNoAnswer();
  const command = useCommand({
    method: "POST",
    path: `${JOURNAL_BATCHES_PATH}/${batch.id}/hand-over`,
    invalidates: [EVERY_JOURNAL_RUN, EVERY_JOURNAL_BATCH],
  });
  const submit = async () => {
    const outcome = await command.submit();
    if (outcome.kind === "accepted") {
      onAccepted(outcome.jobId);
    }
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("journals.batches.handOver.title", { batch: batchLabel(batch) })}
      description={t("journals.batches.handOver.consequence")}
      primaryAction={{
        label: t("journals.batches.handOver.confirm"),
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <RefusalBanner problem={command.problem} />
    </Modal>
  );
}
