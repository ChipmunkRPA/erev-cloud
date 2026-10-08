import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { fetchListPage, type ListPage } from "../../lib/api/lists";
import { type Judgement, JUDGEMENTS_PATH } from "../../lib/api/queries/contracts";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { SelectField } from "../contracts/drawers/common";

async function reviewedRecords(entityId: string, book: string): Promise<readonly Judgement[]> {
  const records: Judgement[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Judgement> = await fetchListPage<Judgement>(
      JUDGEMENTS_PATH,
      {
        entity_id: entityId,
        book,
        topic: "ESTIMATE_VS_ERROR",
        status: "REVIEWED",
      },
      cursor,
      { limit: 200, count: false },
    );
    records.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return records;
}

export function ReopenEvidence({
  entityId,
  book,
  value,
  onChange,
  error,
}: {
  readonly entityId: string;
  readonly book: string;
  readonly value: string | null;
  readonly onChange: (id: string) => void;
  readonly error: string | null;
}) {
  const records = useQuery({
    queryKey: queryKey("contract-judgements", "tenant", {
      entityId,
      book,
      reviewedForReopen: true,
    }),
    queryFn: () => reviewedRecords(entityId, book),
    staleTime: 0,
  });
  const selected = records.data?.find((record) => record.id === value);
  return (
    <section className="flex flex-col gap-3">
      <p className="text-body-sm text-fg-2">{t("close.reopen.evidenceHelp")}</p>
      {records.isError ? (
        <Banner tone="negative" title={t("close.reopen.evidenceLoadError")} />
      ) : null}
      <SelectField
        name="reopen-judgement"
        label={t("close.reopen.evidenceLabel")}
        options={(records.data ?? []).map((record) => ({
          value: record.id,
          label: record.judgement_no,
        }))}
        value={value}
        onChange={onChange}
        error={error}
      />
      {records.isPending ? (
        <p className="text-body-sm text-fg-2">{t("close.reopen.evidenceLoading")}</p>
      ) : null}
      {records.isSuccess && records.data.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("close.reopen.evidenceEmpty")}</p>
      ) : null}
      {selected === undefined ? null : (
        <div className="flex flex-col gap-2 text-body-sm text-fg-1">
          <p className="whitespace-pre-wrap">{selected.conclusion}</p>
          <p className="whitespace-pre-wrap">{selected.rationale}</p>
          <p>
            {t("close.reopen.evidenceReviewer", { name: selected.reviewer?.display_name ?? "—" })}
          </p>
          {selected.contract_id === null ? null : (
            <Link
              className="text-accent-fg hover:underline"
              to={`/contracts/${selected.contract_id}`}
            >
              {t("close.reopen.evidenceContract")}
            </Link>
          )}
        </div>
      )}
    </section>
  );
}
