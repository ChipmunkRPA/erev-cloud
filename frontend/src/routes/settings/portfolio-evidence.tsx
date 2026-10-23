import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { controlClass, Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { type Attachment, sendCommand } from "../../lib/api/queries/contracts";
import { fetchVersionAttachments, versionAttachmentsKey } from "../../lib/api/queries/estimates";
import { useMe } from "../../lib/api/queries/me";
import { t } from "../../lib/i18n/t";
import { EvidenceField, uploadEvidence } from "../contracts/drawers/common";

const label = (key: string) => t(`settings.portfolioEvidence.${key}`);

export function PortfolioEvidence({
  versionId,
  editable,
}: {
  readonly versionId: string;
  readonly editable: boolean;
}) {
  const queryClient = useQueryClient();
  const me = useMe();
  const keys = useCommandKeys();
  const [files, setFiles] = useState<readonly File[]>([]);
  const [round, setRound] = useState(0);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [networkError, setNetworkError] = useState(false);
  // Keep completed uploads across an attach failure. Retrying never reuploads the same File.
  const uploaded = useRef(new Map<File, string>());
  const attachments = useQuery({
    queryKey: versionAttachmentsKey(versionId),
    queryFn: () => fetchVersionAttachments(versionId),
  });
  const attach = async () => {
    if (pending || !editable || files.length === 0) return;
    setPending(true);
    setProblem(null);
    setNetworkError(false);
    try {
      for (const file of files) {
        let fileId = uploaded.current.get(file);
        if (fileId === undefined) {
          const [id] = await uploadEvidence(keys, [file]);
          if (id === undefined) throw new Error("Upload returned no file identity");
          fileId = id;
          uploaded.current.set(file, fileId);
        }
        const result = await sendCommand<Attachment>(keys, "POST", "/api/v1/attachments", {
          subject_type: "estimate_version",
          subject_id: versionId,
          file_object_id: fileId,
          description: null,
        });
        if (!result.ok) {
          setProblem(result.problem);
          return;
        }
        setFiles((current) => current.filter((item) => item !== file));
        uploaded.current.delete(file);
        await queryClient.invalidateQueries({ queryKey: versionAttachmentsKey(versionId) });
      }
      keys.clear();
      setRound((value) => value + 1);
    } catch (error) {
      if (error instanceof ApiProblem) setProblem(error);
      else setNetworkError(true);
    } finally {
      setPending(false);
    }
  };
  return (
    <section className="flex flex-col gap-3" aria-label={label("title")}>
      <h4 className="text-heading-sm">{label("title")}</h4>
      {attachments.isError ? <Banner tone="negative" title={attachments.error.message} /> : null}
      {attachments.isPending ? <p role="status">{label("loading")}</p> : null}
      {attachments.data?.length === 0 ? <p>{label("empty")}</p> : null}
      <ul className="flex flex-col gap-3">
        {(attachments.data ?? []).map((item) => (
          <li key={item.id}>
            <a
              className="text-accent-fg underline"
              href={`/api/v1/files/${item.file_object_id}/content`}
            >
              {item.original_filename ?? item.id}
            </a>
            {editable && item.created_by_kind === "USER" && item.created_by === me.data?.user.id ? (
              <VoidEvidence attachment={item} />
            ) : null}
          </li>
        ))}
      </ul>
      {editable ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void attach();
          }}
        >
          <RefusalBanner problem={problem} />
          {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
          <fieldset disabled={pending}>
            <EvidenceField
              key={round}
              name="portfolio-evidence-files"
              label={label("files")}
              files={files}
              onChange={setFiles}
            />
          </fieldset>
          <Button
            type="submit"
            loading={pending}
            disabledReason={files.length ? undefined : label("chooseFile")}
          >
            {label("attach")}
          </Button>
        </form>
      ) : null}
    </section>
  );
}

function VoidEvidence({ attachment }: { readonly attachment: Attachment }) {
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `/api/v1/attachments/${attachment.id}/void`,
    invalidates: [versionAttachmentsKey(attachment.subject_id)],
  });
  if (!open)
    return (
      <Button size="sm" onClick={() => setOpen(true)}>
        {label("void")}
      </Button>
    );
  return (
    <form
      className="flex max-w-120 flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (command.pending || !reason.trim()) return;
        setNetworkError(false);
        void command.submit({ reason: reason.trim() }).then((result) => {
          if (result.kind === "network-error") setNetworkError(true);
        });
      }}
    >
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      <Field name={`portfolio-evidence-reason-${attachment.id}`} label={label("reason")} required>
        {(control) => (
          <input
            {...control}
            className={controlClass(false)}
            value={reason}
            disabled={command.pending}
            onChange={(e) => setReason(e.target.value)}
          />
        )}
      </Field>
      <div className="flex gap-2">
        <Button
          type="submit"
          loading={command.pending}
          disabledReason={reason.trim() ? undefined : label("reasonRequired")}
        >
          {label("confirmVoid")}
        </Button>
        <Button
          disabledReason={command.pending ? label("saving") : undefined}
          onClick={() => setOpen(false)}
        >
          {label("cancel")}
        </Button>
      </div>
    </form>
  );
}
