import { Link } from "react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { Banner } from "../../../components/feedback/Banner";
import { Button } from "../../../components/ui/Button";
import { Field } from "../../../components/form/Field";
import { MultiSelect } from "../../../components/form/MultiSelect";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  CONTRACTS_PATH,
  CONTRACT_RECORD_KEYS,
  type Contract,
  EMPTY_CONTRACT_QUERY,
  contractsKey,
  fetchContractsPage,
} from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { placeProblem } from "../../../lib/api/refusals";
import { t } from "../../../lib/i18n/t";
import { RadioGroup, SelectField, TextField } from "./common";

const MEMBERS = {
  target: ["target_contract_id"],
  lines: ["obligation_keys"],
  comment: ["comment"],
} as const;

export function RegroupDrawer({
  contract,
  obligations,
  onClose,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly onClose: () => void;
}) {
  const active = contract.status === "ACTIVE";
  const [prepared, setPrepared] = useState<readonly string[] | null>(null);
  const formId = useId();
  const toast = useToast();
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [destination, setDestination] = useState<"new" | "existing">(active ? "existing" : "new");
  const [target, setTarget] = useState<string | null>(null);
  const query = {
    ...EMPTY_CONTRACT_QUERY,
    entity: [contract.contracting_entity.code],
    status: [active ? "ACTIVE" : "DRAFT"],
  };
  const targets = useInfiniteQuery({
    queryKey: [...contractsKey(query), "regroup-targets"],
    queryFn: ({ pageParam }) => fetchContractsPage(query, pageParam, null),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: destination === "existing",
    retry: false,
  });
  const candidates = (targets.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (item) =>
      item.id !== contract.id &&
      item.status === (active ? "ACTIVE" : "DRAFT") &&
      item.contracting_entity.id === contract.contracting_entity.id &&
      item.transaction_currency === contract.transaction_currency,
  );
  const targetValid =
    destination === "new" ||
    (targets.isSuccess && !targets.isFetching && candidates.some((item) => item.id === target));
  const command = useCommand<{ modification_ids: string[] }>({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contract.id}/regroup`,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(() => placeProblem(command.problem, MEMBERS), [command.problem]);
  const options = obligations.map((item) => ({
    value: item.obligation_key,
    label: `${item.obligation_key} · ${item.product.name}`,
  }));
  const valid =
    (contract.status === "DRAFT" || active) &&
    targetValid &&
    selected.length > 0 &&
    comment.trim() !== "" &&
    selected.every((key) => options.some((option) => option.value === key));
  const submit = async () => {
    setAttempted(true);
    if (!valid || command.pending) return;
    const outcome = await command.submit({
      obligation_keys: selected,
      comment: comment.trim(),
      ...(destination === "existing" ? { target_contract_id: target } : {}),
    });
    if (outcome.kind === "succeeded") {
      if (active) {
        setPrepared(outcome.data?.modification_ids ?? []);
        return;
      }
      toast.show({
        tone: "positive",
        message: t(
          destination === "new"
            ? "contracts.drawer.regroup.saved"
            : "contracts.drawer.regroup.savedExisting",
        ),
      });
      onClose();
    }
  };
  return (
    <Drawer
      open
      title={t(
        active ? "contracts.drawer.regroup.transferTitle" : "contracts.drawer.regroup.title",
      )}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={!prepared && (selected.length > 0 || comment !== "")}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={
        prepared
          ? undefined
          : {
              label: t(
                active ? "contracts.drawer.regroup.prepare" : "contracts.drawer.regroup.move",
              ),
              form: formId,
            }
      }
      onClose={onClose}
    >
      {prepared ? (
        <section className="flex flex-col gap-3">
          <p>{t("contracts.drawer.regroup.prepared")}</p>
          {prepared.map((id, index) => (
            <Link
              key={id}
              className="text-accent-fg underline"
              onClick={onClose}
              to={`/contracts/${index === 0 ? contract.id : target}/modifications/${id}`}
            >
              {t(
                index === 0
                  ? "contracts.drawer.regroup.reviewSource"
                  : "contracts.drawer.regroup.reviewTarget",
              )}
            </Link>
          ))}
        </section>
      ) : (
        <form
          id={formId}
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <p>
            {t(active ? "contracts.drawer.regroup.transferHelp" : "contracts.drawer.regroup.help")}
          </p>
          <fieldset
            disabled={command.pending || (!active && contract.status !== "DRAFT")}
            className="flex flex-col gap-4"
          >
            {!active && (
              <RadioGroup
                legend={t("contracts.drawer.regroup.destination")}
                value={destination}
                options={[
                  { value: "new", label: t("contracts.drawer.regroup.new") },
                  { value: "existing", label: t("contracts.drawer.regroup.existing") },
                ]}
                onChange={setDestination}
              />
            )}
            {destination === "existing" ? (
              <>
                <SelectField
                  name="regroup-target"
                  label={t("contracts.drawer.regroup.target")}
                  options={candidates.map((item) => ({ value: item.id, label: item.external_id }))}
                  value={target}
                  onChange={setTarget}
                  error={
                    attempted && !targetValid ? t("contracts.drawer.choose") : placed.fields.target
                  }
                />
                {targets.isPending ? (
                  <p role="status">
                    {t(
                      active
                        ? "contracts.drawer.regroup.loadingActive"
                        : "contracts.drawer.regroup.loading",
                    )}
                  </p>
                ) : null}
                {targets.isSuccess && candidates.length === 0 && !targets.hasNextPage ? (
                  <p>
                    {t(
                      active
                        ? "contracts.drawer.regroup.emptyActive"
                        : "contracts.drawer.regroup.empty",
                    )}
                  </p>
                ) : null}
                {targets.isError ? (
                  <Banner
                    tone="negative"
                    title={t(
                      active
                        ? "contracts.drawer.regroup.loadErrorActive"
                        : "contracts.drawer.regroup.loadError",
                    )}
                    actions={
                      <Button
                        onClick={() =>
                          void (targets.isFetchNextPageError
                            ? targets.fetchNextPage()
                            : targets.refetch())
                        }
                      >
                        {t("common.grid.retry")}
                      </Button>
                    }
                  />
                ) : null}
                {targets.hasNextPage ? (
                  <Button loading={targets.isFetching} onClick={() => void targets.fetchNextPage()}>
                    {t(
                      active
                        ? "contracts.drawer.regroup.moreActive"
                        : "contracts.drawer.regroup.more",
                    )}
                  </Button>
                ) : null}
              </>
            ) : null}
            <Field
              name="regroup-lines"
              label={t("contracts.drawer.regroup.lines")}
              error={
                attempted && selected.length === 0
                  ? t("contracts.drawer.choose")
                  : placed.fields.lines
              }
            >
              {(control) => (
                <MultiSelect
                  control={control}
                  options={options}
                  values={selected}
                  onChange={setSelected}
                  invalid={attempted && selected.length === 0}
                />
              )}
            </Field>
            <TextField
              name="regroup-comment"
              label={t("contracts.drawer.comment")}
              required
              multiline
              value={comment}
              onChange={setComment}
              error={
                attempted && comment.trim() === ""
                  ? t("contracts.drawer.commentRequired")
                  : placed.fields.comment
              }
            />
          </fieldset>
        </form>
      )}
    </Drawer>
  );
}
