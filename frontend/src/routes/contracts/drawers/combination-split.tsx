import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Banner } from "../../../components/feedback/Banner";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { DateInput } from "../../../components/form/DateInput";
import { Field } from "../../../components/form/Field";
import { MultiSelect } from "../../../components/form/MultiSelect";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { ApiProblem } from "../../../lib/api/problems";
import { readJson, type Contract } from "../../../lib/api/queries/contracts";
import { queryKey } from "../../../lib/api/query-keys";
import type { components } from "../../../lib/api/schema";
import { formatMoney, parseDateInput } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { SelectField } from "./common";

const label = (key: string) => t(`contracts.drawer.split.${key}`);
type Preview = components["schemas"]["CombinationSplitPreviewOut"];
type Group = components["schemas"]["CombinationGroupDetailOut"];

function amount(minor: number, preview: Preview) {
  if (!Number.isSafeInteger(minor)) return label("amountUnavailable");
  const digits = preview.currency_minor_unit;
  const negative = minor < 0;
  const raw = BigInt(Math.abs(minor))
    .toString()
    .padStart(digits + 1, "0");
  const decimal = digits ? `${raw.slice(0, -digits)}.${raw.slice(-digits)}` : raw;
  return formatMoney(`${negative ? "-" : ""}${decimal}`, preview.currency);
}

export function CombinationSplitDrawer({
  contract,
  onClose,
}: {
  readonly contract: Contract;
  readonly onClose: () => void;
}) {
  const path = `/api/v1/combination-groups/${contract.combination_group.id}`;
  const [date, setDate] = useState("");
  const [book, setBook] = useState<string | null>("ASC606");
  const [leaving, setLeaving] = useState<readonly string[]>([]);
  const [request, setRequest] = useState<{ query: string; nonce: number } | null>(null);
  const members = useQuery({
    queryKey: queryKey("contracts", "tenant", { path, view: "split-members" }),
    queryFn: async () => {
      const group = (await readJson<Group>(path)).data;
      if (group.member_count !== group.member_contract_ids.length)
        throw new Error("incomplete population");
      return Promise.all(
        group.member_contract_ids.map(
          async (id) => (await readJson<Contract>(`/api/v1/contracts/${id}`)).data,
        ),
      );
    },
    retry: false,
  });
  const preview = useQuery({
    queryKey: queryKey("contracts", "tenant", {
      path,
      view: "split-preview",
      query: request?.query ?? null,
      nonce: request?.nonce ?? null,
    }),
    queryFn: async () => {
      if (!request) throw new Error("No split requested");
      return (await readJson<Preview>(`${path}/split-preview?${request.query}`)).data;
    },
    enabled: request !== null,
    retry: false,
  });
  const parsed = parseDateInput(date);
  const ready =
    members.isSuccess &&
    !members.isFetching &&
    parsed.ok &&
    book !== null &&
    leaving.length > 0 &&
    leaving.every((id) => members.data.some((m) => m.id === id));
  const result = request && !preview.isFetching && !preview.isError ? preview.data : undefined;
  const error = members.error ?? preview.error;
  return (
    <Drawer open title={label("title")} subtitle={contract.external_id} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p>{label("help")}</p>
        {members.isPending ? <p role="status">{label("loading")}</p> : null}
        {error instanceof ApiProblem ? (
          <RefusalBanner problem={error} />
        ) : error ? (
          <Banner tone="negative" title={label("loadError")} />
        ) : null}
        {members.isError ? (
          <Button onClick={() => void members.refetch()}>{label("retry")}</Button>
        ) : null}
        <Field label={label("date")} name="split-date">
          {(control) => (
            <DateInput
              control={control}
              value={date}
              onChange={(value) => {
                setDate(value);
                setRequest(null);
              }}
            />
          )}
        </Field>
        <SelectField
          name="split-book"
          label={label("book")}
          value={book}
          options={[
            { value: "ASC606", label: "ASC606" },
            { value: "IFRS15", label: "IFRS15" },
          ]}
          onChange={(value) => {
            setBook(value);
            setRequest(null);
          }}
        />
        <Field label={label("members")} name="split-members">
          {(control) => (
            <MultiSelect
              control={control}
              values={leaving}
              options={(members.data ?? []).map((m) => ({ value: m.id, label: m.external_id }))}
              onChange={(value) => {
                setLeaving(value);
                setRequest(null);
              }}
            />
          )}
        </Field>
        <Button
          disabledReason={ready ? undefined : label("required")}
          loading={preview.isFetching}
          onClick={() => {
            if (!ready || !parsed.ok || book === null) return;
            const params = new URLSearchParams({ effective_date: parsed.value, book_code: book });
            [...leaving].sort().forEach((id) => params.append("leave_contract_ids", id));
            setRequest((old) => ({ query: params.toString(), nonce: (old?.nonce ?? 0) + 1 }));
          }}
        >
          {label("calculate")}
        </Button>
        {result ? (
          <section className="flex flex-col gap-3" aria-label={label("results")}>
            <p>
              {result.effective_date} · {result.book_code} · {result.currency}
            </p>
            <p>
              {label("recognized")}: {amount(result.recognized_minor, result)} ·{" "}
              {label("remaining")}: {amount(result.unrecognized_minor, result)}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-body-sm">
                <caption>{label("results")}</caption>
                <thead>
                  <tr>
                    {["contract", "destination", "recognized", "before", "after", "ssp"].map(
                      (key) => (
                        <th className="p-2" scope="col" key={key}>
                          {label(key)}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {result.members.map((member) => (
                    <tr key={member.contract_id}>
                      <td className="p-2">{member.contract_key}</td>
                      <td className="p-2">
                        {member.destination.startsWith("SINGLETON:")
                          ? label("separate")
                          : label("retained")}
                      </td>
                      <td className="p-2">{amount(member.recognized_minor, result)}</td>
                      <td className="p-2">{amount(member.remaining_before_minor, result)}</td>
                      <td className="p-2">{amount(member.remaining_after_minor, result)}</td>
                      <td className="p-2">{member.remaining_ssp}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.members.map((member) => (
              <details key={member.contract_id}>
                <summary>
                  {member.contract_key} · {label("sources")}
                </summary>
                {member.obligations.map((ob) => (
                  <div className="my-2" key={ob.obligation_key}>
                    <p>
                      {ob.obligation_key}: {amount(ob.remaining_before_minor, result)} →{" "}
                      {amount(ob.remaining_after_minor, result)} · {label("ssp")}:{" "}
                      {ob.remaining_ssp}
                    </p>
                    <ul>
                      {ob.ssp_sources.map((source, index) => (
                        <li key={index}>{String(source.ref_id ?? "")}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </details>
            ))}
            <details>
              <summary>{label("evidence")}</summary>
              <p className="break-all">{result.source_computation_id}</p>
              <p className="break-all">{result.input_sha256}</p>
              <p className="break-all">{result.output_sha256}</p>
            </details>
          </section>
        ) : null}
      </div>
    </Drawer>
  );
}
