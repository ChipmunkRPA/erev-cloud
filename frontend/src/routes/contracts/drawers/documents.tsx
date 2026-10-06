// Documents drawer (SCREENS §4.8; 04 API-R-12 `GET /attachments`, `POST /files`, `POST /attachments`,
// `POST /attachments/{id}/void`, `GET /files/{id}/content`). "Contract reference", the attachments of the
// contract (File, Description, Size, SHA-256, Uploaded by, Uploaded at) with "Void attachment", and the
// footer "Upload document". The second table "Evidence on events and estimates" needs
// `GET /attachments?contract_id=`, which the route does not take, so it is not rendered (L5-4-Q-31).
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { EmptyState } from "../../../components/feedback/EmptyState";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../../components/form/ReasonField";
import { CopySimple } from "../../../components/icons/registry";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { Modal } from "../../../components/ui/Modal";
import { useCommandKeys } from "../../../lib/api/commands";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  type Attachment,
  ATTACHMENTS_PATH,
  type Contract,
  documentsKey,
  fetchDocuments,
  sendCommand,
} from "../../../lib/api/queries/contracts";
import { FILE_CONTENT_PATH } from "../../../lib/api/queries/approvals";
import { formatNumber, formatTimestamp, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { ReadOnlyItem, uploadEvidence, useRefreshRecord } from "./common";

/** ERR-37: 25 MiB. */
export const DOCUMENT_LIMIT_BYTES = 25 * 1024 * 1024;

/** DS-FMT-23 middle ellipsis of a digest. */
export function middleEllipsis(value: string): string {
  return value.length <= 20 ? value : `${value.slice(0, 8)}…${value.slice(-8)}`;
}

export interface DocumentsDrawerProps {
  readonly contract: Contract;
  readonly canUpload: boolean;
  readonly onClose: () => void;
}

export function DocumentsDrawer({ contract, canUpload, onClose }: DocumentsDrawerProps) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [voiding, setVoiding] = useState<Attachment | null>(null);
  const documents = useQuery({
    queryKey: documentsKey(contract.id),
    queryFn: () => fetchDocuments(contract.id),
  });
  const items = documents.data?.items ?? [];

  const upload = async (file: File) => {
    if (file.size > DOCUMENT_LIMIT_BYTES) {
      toast.show({ tone: "negative", message: t("contracts.documents.accepted") });
      return;
    }
    setUploading(true);
    setProblem(null);
    try {
      const [fileId] = await uploadEvidence(keys, [file]);
      const created = await sendCommand(keys, "POST", ATTACHMENTS_PATH, {
        subject_type: "contract",
        subject_id: contract.id,
        file_object_id: fileId,
        description: null,
      });
      if (!created.ok) {
        setProblem(created.problem);
        return;
      }
      await refresh();
      toast.show({
        tone: "positive",
        message: t("contracts.documents.uploaded", { name: file.name }),
      });
    } catch (error) {
      if (error instanceof Error && error.name === "ApiProblem") {
        setProblem(error as ApiProblem);
      } else {
        // No answer: the same file chosen again is sent under the same keys (DG-FE-05).
        noAnswer();
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <Drawer
      open
      wide
      title={t("contracts.documents.title")}
      subtitle={contract.external_id}
      initialFocus="title"
      submitting={uploading}
      banner={<RefusalBanner problem={problem} />}
      primaryAction={
        canUpload
          ? { label: t("contracts.documents.upload"), onAction: () => input.current?.click() }
          : undefined
      }
      onClose={onClose}
    >
      <div data-testid="SF-03-drawer-documents" className="flex flex-col gap-4">
        <dl>
          <ReadOnlyItem label={t("contracts.documents.reference")}>
            {contract.document_ref ?? t("contracts.documents.notSet")}
          </ReadOnlyItem>
        </dl>
        <p className="text-body-sm text-fg-3">{t("contracts.documents.accepted")}</p>
        <input
          ref={input}
          type="file"
          aria-label={t("contracts.documents.upload")}
          accept=".pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.eml"
          className="sr-only"
          tabIndex={-1}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file !== undefined) {
              void upload(file);
            }
          }}
        />
        {documents.isPending ? (
          <Skeleton region={t("contracts.documents.title")} shape="rows" count={3} />
        ) : items.length === 0 ? (
          <EmptyState
            title={t("contracts.documents.emptyTitle")}
            description={t("contracts.documents.empty")}
            headingLevel={3}
          />
        ) : (
          <table className="w-full border-collapse text-body-sm">
            <caption className="sr-only">{t("contracts.documents.title")}</caption>
            <thead>
              <tr className="border-b border-default text-caption text-fg-3">
                {["file", "description", "size", "sha", "uploadedBy", "uploadedAt"].map(
                  (column) => (
                    <th key={column} scope="col" className="py-1 pe-3 text-start font-medium">
                      {t(`contracts.documents.column.${column}`)}
                    </th>
                  ),
                )}
                {canUpload ? (
                  <th scope="col" className="py-1 text-start font-medium">
                    <span className="sr-only">{t("contracts.documents.column.actions")}</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-b border-hairline align-top">
                  <th scope="row" className="py-1 pe-3 text-start font-normal">
                    <a
                      href={`${FILE_CONTENT_PATH}/${item.file_object_id}/content`}
                      className="text-fg-1 underline decoration-control decoration-dotted underline-offset-3"
                    >
                      {item.original_filename ?? item.file_object_id}
                    </a>
                  </th>
                  <td className="py-1 pe-3">{item.description ?? NO_VALUE}</td>
                  <td className="num py-1 pe-3 text-end">
                    {t("contracts.documents.size", {
                      size: formatNumber(item.size_bytes, { kind: "count" }),
                    })}
                  </td>
                  <td className="py-1 pe-3">
                    <span className="inline-flex items-center gap-1 font-mono text-mono-sm">
                      {middleEllipsis(item.sha256)}
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={CopySimple}
                        aria-label={t("contracts.documents.copySha")}
                        onClick={() => void navigator.clipboard.writeText(item.sha256)}
                      />
                    </span>
                  </td>
                  <td className="py-1 pe-3">
                    {t(`contracts.documents.principal.${item.created_by_kind}`)}
                  </td>
                  <td className="py-1 pe-3" data-volatile="">
                    {formatTimestamp(item.created_at)}
                  </td>
                  {canUpload ? (
                    <td className="py-1">
                      {item.voided_at === null ? (
                        <Button variant="link" onClick={() => setVoiding(item)}>
                          {t("contracts.documents.void")}
                        </Button>
                      ) : (
                        <span className="text-fg-3">{t("common.status.void")}</span>
                      )}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {voiding === null ? null : (
        <VoidAttachmentModal attachment={voiding} onClose={() => setVoiding(null)} />
      )}
    </Drawer>
  );
}

function VoidAttachmentModal({
  attachment,
  onClose,
}: {
  readonly attachment: Attachment;
  readonly onClose: () => void;
}) {
  const refresh = useRefreshRecord();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    setSubmitting(true);
    try {
      const outcome = await sendCommand(keys, "POST", `${ATTACHMENTS_PATH}/${attachment.id}/void`, {
        reason: reason.trim(),
      });
      if (!outcome.ok) {
        setProblem(outcome.problem);
        return;
      }
      await refresh();
      toast.show({ tone: "positive", message: t("contracts.documents.voided") });
      onClose();
    } catch {
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("contracts.documents.voidTitle", {
        name: attachment.original_filename ?? attachment.file_object_id,
      })}
      description={t("contracts.documents.voidDescription")}
      submitting={submitting}
      primaryAction={{
        label: t("contracts.documents.void"),
        destructive: true,
        onAction: () => void submit(),
      }}
      onClose={onClose}
    >
      <RefusalBanner problem={problem} />
      <ReasonField
        name="attachment-void-reason"
        label={t("contracts.list.hold.reason")}
        value={reason}
        onChange={setReason}
        showError={attempted}
      />
    </Modal>
  );
}
