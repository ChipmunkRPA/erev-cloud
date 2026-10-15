import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Combobox } from "../../components/form/Combobox";
import { Field } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage, type ListPage } from "../../lib/api/lists";
import { isRefused } from "../../lib/api/problems";
import { queryKey } from "../../lib/api/query-keys";
import {
  EVIDENCE_PACKS_PATH,
  evidencePackRoute,
  mayChooseEvidenceSources,
  mayCreateEvidence,
} from "../../lib/api/queries/evidence-packs";
import { fetchPeriodLocks, locksKey } from "../../lib/api/queries/periods";
import {
  ENTITIES_PATH,
  PERIODS_PATH,
  type Entity,
  type Period,
  periodLabel,
} from "../../lib/api/queries/tenant";
import type { components } from "../../lib/api/schema";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { bookLabel } from "../reports/viewer/RunStamp";

// These selectors follow every cursor: older periods and entities beyond the shell's
// first 200 choices must remain available for historical evidence generation.
async function entities(): Promise<readonly Entity[]> {
  const result: Entity[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Entity> = await fetchListPage<Entity>(ENTITIES_PATH, {}, cursor, {
      count: false,
    });
    result.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return result;
}
async function periods(entity: string, book: string): Promise<readonly Period[]> {
  const result: Period[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Period> = await fetchListPage<Period>(
      PERIODS_PATH,
      { entity, book },
      cursor,
      {
        count: false,
      },
    );
    result.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return result;
}
const retry = (count: number, error: unknown) => !isRefused(error) && count < 1;

export function GenerateClosePack() {
  const access = useAccess();
  const navigate = useNavigate();
  const location = useLocation();
  const formId = useId();
  const initial = new URLSearchParams(location.search);
  const [open, setOpen] = useState(false);
  const [entityCode, setEntityCode] = useState<string | null>(initial.get("entity"));
  const [book, setBook] = useState<string | null>(initial.get("book"));
  const [periodKey, setPeriodKey] = useState<string | null>(initial.get("period"));
  const [lockId, setLockId] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: EVIDENCE_PACKS_PATH,
    invalidates: [queryKey("evidence-packs", "tenant")],
  });
  const enabled = open && mayChooseEvidenceSources(access);
  const entityQuery = useQuery({
    queryKey: queryKey("evidence-source-entities", "tenant"),
    queryFn: entities,
    enabled,
    retry,
  });
  const allowed = (entityQuery.data ?? []).filter(
    (entity) =>
      mayCreateEvidence(access, entity.id) && access.holds("config.read", { id: entity.id }),
  );
  const entity = allowed.find((item) => item.code === entityCode);
  const books = entity?.books ?? [];
  const validBook = books.some((item) => item.book_code === book);
  const periodQuery = useQuery({
    queryKey: queryKey("evidence-source-periods", "tenant", { entity: entityCode, book }),
    queryFn: () => periods(entityCode ?? "", book ?? ""),
    enabled: enabled && entity !== undefined && validBook,
    retry,
  });
  const choices =
    entity === undefined || !validBook
      ? []
      : (periodQuery.data ?? []).filter(
          (item) => item.entity.id === entity.id && item.book === book,
        );
  const period = choices.find((item) => item.period.period_key === periodKey);
  const lockQuery = useQuery({
    queryKey: locksKey(period?.id ?? ""),
    queryFn: () => fetchPeriodLocks(period?.id ?? ""),
    enabled: enabled && period !== undefined,
    retry,
  });
  const locks =
    period === undefined
      ? []
      : (lockQuery.data ?? []).filter(
          (item) =>
            item.kind === "LOCK" &&
            item.previous_lock_id === null &&
            item.snapshot_manifest_sha256 !== null,
        );
  const lock = locks.find((item) => item.id === lockId);
  const busy = command.pending || accepted;
  const readError = entityQuery.error ?? periodQuery.error ?? lockQuery.error;
  const body: components["schemas"]["ClosePackCreateIn"] | null =
    entity !== undefined && period !== undefined && lock !== undefined
      ? {
          kind: "CLOSE",
          entity_code: entity.code,
          book: period.book,
          period_key: period.period.period_key,
          period_lock_id: lock.id,
        }
      : null;
  async function submit() {
    if (body === null || busy || readError !== null) return;
    setNetworkError(false);
    const outcome = await command.submit(body);
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      setAccepted(true);
      const packId = outcome.response.headers.get("X-Erev-Evidence-Pack-Id");
      if (packId !== null && packId !== "") void navigate(evidencePackRoute(packId));
    } else if (outcome.kind === "network-error") setNetworkError(true);
  }
  if (!mayChooseEvidenceSources(access)) return null;
  return (
    <>
      <Button onClick={() => setOpen(true)}>{t("evidence.generate.open")}</Button>
      <Modal
        open={open}
        variant="form"
        title={t("evidence.generate.title")}
        description={t("evidence.generate.description")}
        onClose={() => {
          if (!command.pending) setOpen(false);
        }}
        submitting={command.pending}
        testId="SF-09-dialog-generate-close"
        primaryAction={{
          label: t("evidence.generate.submit"),
          form: formId,
          disabledReason: accepted
            ? t("evidence.generate.accepted")
            : body === null || readError !== null
              ? t("evidence.generate.choose")
              : undefined,
        }}
      >
        <form
          id={formId}
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
          className="space-y-4"
        >
          <RefusalBanner problem={command.problem} />
          {entityQuery.isFetching || periodQuery.isFetching || lockQuery.isFetching ? (
            <p role="status">{t("evidence.generate.loading")}</p>
          ) : null}
          {readError === null ? null : (
            <Banner
              tone="negative"
              title={t("evidence.generate.loadError")}
              actions={
                <Button
                  onClick={() => {
                    void entityQuery.refetch();
                    if (entity && validBook) void periodQuery.refetch();
                    if (period) void lockQuery.refetch();
                  }}
                >
                  {t("evidence.packs.retry")}
                </Button>
              }
            />
          )}
          {networkError ? (
            <Banner tone="negative" title={t("evidence.generate.networkError")} />
          ) : null}
          {accepted ? <Banner tone="info" title={t("evidence.generate.accepted")} /> : null}
          <fieldset disabled={busy} className="space-y-4">
            <Field name="evidence-entity" label={t("evidence.packs.entity")} required>
              {(control) => (
                <Combobox
                  control={control}
                  value={entityCode}
                  options={allowed.map((item) => ({
                    value: item.code,
                    label: item.is_active
                      ? `${item.code} — ${item.name}`
                      : t("evidence.generate.inactive", { name: `${item.code} — ${item.name}` }),
                  }))}
                  onChange={(value) => {
                    setEntityCode(value);
                    setBook(null);
                    setPeriodKey(null);
                    setLockId(null);
                  }}
                />
              )}
            </Field>
            <Field name="evidence-book" label={t("evidence.packs.book")} required>
              {(control) => (
                <Combobox
                  control={control}
                  value={book}
                  options={books.map((item) => ({
                    value: item.book_code,
                    label: item.is_enabled
                      ? bookLabel(item.book_code)
                      : t("evidence.generate.inactive", { name: bookLabel(item.book_code) }),
                  }))}
                  onChange={(value) => {
                    setBook(value);
                    setPeriodKey(null);
                    setLockId(null);
                  }}
                />
              )}
            </Field>
            <Field name="evidence-period" label={t("evidence.packs.period")} required>
              {(control) => (
                <Combobox
                  control={control}
                  value={periodKey}
                  options={choices.map((item) => ({
                    value: item.period.period_key,
                    label: periodLabel(item.period),
                  }))}
                  onChange={(value) => {
                    setPeriodKey(value);
                    setLockId(null);
                  }}
                />
              )}
            </Field>
            <Field
              name="evidence-lock"
              label={t("evidence.generate.lock")}
              required
              help={t("evidence.generate.lockHelp")}
            >
              {(control) => (
                <Combobox
                  control={control}
                  value={lockId}
                  options={locks.map((item) => ({
                    value: item.id,
                    label: `${item.approval_request_no ?? item.id} — ${formatTimestamp(item.created_at)}`,
                  }))}
                  onChange={(value) => {
                    setLockId(value);
                  }}
                />
              )}
            </Field>
          </fieldset>
          {period !== undefined && lockQuery.isSuccess && locks.length === 0 ? (
            <p role="status">{t("evidence.generate.noLocks")}</p>
          ) : null}
        </form>
      </Modal>
    </>
  );
}
