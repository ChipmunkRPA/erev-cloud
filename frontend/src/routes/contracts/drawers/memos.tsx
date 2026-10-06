// Edit memos (SCREENS §4.9.5; 04 ACT-06 `POST /contracts/{id}/update-memos`; BR-CON-02). Level contract
// or one obligation, Memo 1 to 3, custom attribute rows, one value per dimension and a required
// comment, with `If-Match`. Posted amounts do not change.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  type Contract,
  contractIfMatch,
  CONTRACT_RECORD_KEYS,
  CONTRACTS_PATH,
} from "../../../lib/api/queries/contracts";
import {
  dimensionsKey,
  dimensionValuesKey,
  fetchAllDimensions,
  fetchDimensionValues,
} from "../../../lib/api/queries/dimensions";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { placeProblem } from "../../../lib/api/refusals";
import { t } from "../../../lib/i18n/t";
import { type Choice, RadioGroup, SelectField, TextField } from "./common";

type Level = "CONTRACT" | "OBLIGATION";

// docs/dev-guide.md DG-FE-06: the fields of the drawer and the members of the body each sends. The
// attribute rows and the dimension selects show none, so an error on their members is the banner's.
const MEMO_MEMBERS = {
  obligation: ["obligation_key"],
  memo1: ["memo_1"],
  memo2: ["memo_2"],
  memo3: ["memo_3"],
  comment: ["comment"],
} as const;
// At contract level no obligation is on screen.
const MEMO_MEMBERS_OF_CONTRACT = { ...MEMO_MEMBERS, obligation: [] } as const;
const MEMO_FIELD = ["memo1", "memo2", "memo3"] as const;

interface AttributeRow {
  readonly id: number;
  readonly key: string;
  readonly value: string;
}

export interface EditMemosDrawerProps {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly obligationKey?: string | undefined;
  readonly onClose: () => void;
}

export function EditMemosDrawer({
  contract,
  obligations,
  obligationKey,
  onClose,
}: EditMemosDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const [level, setLevel] = useState<Level>(
    obligationKey === undefined ? "CONTRACT" : "OBLIGATION",
  );
  const [key, setKey] = useState<string | null>(obligationKey ?? null);
  const source =
    level === "OBLIGATION" ? obligations.find((item) => item.obligation_key === key) : undefined;
  const [memos, setMemos] = useState<readonly [string, string, string]>(() => {
    const record = obligationKey === undefined ? contract : source;
    return [record?.memo_1 ?? "", record?.memo_2 ?? "", record?.memo_3 ?? ""];
  });
  const [rows, setRows] = useState<readonly AttributeRow[]>(() =>
    Object.entries(contract.custom_attributes).map(([name, value], index) => ({
      id: index,
      key: name,
      value: typeof value === "string" ? value : JSON.stringify(value),
    })),
  );
  const [dimensionValues, setDimensionValues] = useState<Readonly<Record<string, string>>>({});
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const dimensions = useQuery({ queryKey: dimensionsKey(), queryFn: fetchAllDimensions });
  const active = (dimensions.data ?? []).filter((item) => item.is_active);
  const values = useQueries({
    queries: active.map((dimension) => ({
      queryKey: dimensionValuesKey(dimension.code),
      queryFn: () => fetchDimensionValues(dimension.code),
    })),
  });
  const command = useCommand({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contract.id}/update-memos`,
    ifMatch: contractIfMatch(contract.head_stream_version),
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof MEMO_MEMBERS>(
        command.problem,
        level === "OBLIGATION" ? MEMO_MEMBERS : MEMO_MEMBERS_OF_CONTRACT,
      ),
    [command.problem, level],
  );
  const levels: readonly Choice<Level>[] = [
    { value: "CONTRACT", label: t("contracts.drawer.level.contract") },
    { value: "OBLIGATION", label: t("contracts.drawer.level.obligation") },
  ];
  const keys: readonly Choice<string>[] = obligations.map((item) => ({
    value: item.obligation_key,
    label: `${item.obligation_key} · ${item.product.name}`,
  }));

  const submit = async () => {
    setAttempted(true);
    if (comment.trim() === "" || (level === "OBLIGATION" && key === null)) {
      return;
    }
    const attributes = Object.fromEntries(
      rows.filter((row) => row.key.trim() !== "").map((row) => [row.key.trim(), row.value]),
    );
    const outcome = await command.submit({
      obligation_key: level === "OBLIGATION" ? key : null,
      memo_1: memos[0] === "" ? null : memos[0],
      memo_2: memos[1] === "" ? null : memos[1],
      memo_3: memos[2] === "" ? null : memos[2],
      custom_attributes: level === "CONTRACT" ? attributes : null,
      dimensions: Object.keys(dimensionValues).length === 0 ? null : dimensionValues,
      comment: comment.trim(),
    });
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({ tone: "positive", message: t("contracts.drawer.memos.saved") });
      onClose();
    }
  };

  const setMemo = (index: 0 | 1 | 2, text: string) =>
    setMemos((current) => {
      const next: [string, string, string] = [current[0], current[1], current[2]];
      next[index] = text;
      return next;
    });

  return (
    <Drawer
      open
      title={t("contracts.drawer.memos.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={comment !== ""}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={{ label: t("contracts.drawer.memos.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-edit-memos"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RadioGroup
          legend={t("contracts.drawer.level.label")}
          options={levels}
          value={level}
          onChange={setLevel}
        />
        {level === "OBLIGATION" ? (
          <SelectField
            name="memos-obligation"
            label={t("contracts.drawer.obligation")}
            options={keys}
            value={key}
            onChange={setKey}
            error={
              attempted && key === null ? t("contracts.drawer.choose") : placed.fields.obligation
            }
          />
        ) : null}
        {([0, 1, 2] as const).map((index) => (
          <TextField
            key={index}
            name={`memos-memo-${String(index + 1)}`}
            label={t("contracts.drawer.memos.memo", { position: index + 1 })}
            optional
            value={memos[index]}
            onChange={(text) => setMemo(index, text)}
            error={placed.fields[MEMO_FIELD[index]]}
          />
        ))}
        {level === "CONTRACT" ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-body-sm font-medium text-fg-1">
              {t("contracts.drawer.memos.attributes")}
            </legend>
            {rows.map((row, index) => (
              <div key={row.id} className="flex items-end gap-2">
                <TextField
                  name={`memos-attribute-key-${String(row.id)}`}
                  label={t("contracts.drawer.memos.attributeKey", { position: index + 1 })}
                  width="money"
                  value={row.key}
                  onChange={(text) =>
                    setRows((current) =>
                      current.map((item) => (item.id === row.id ? { ...item, key: text } : item)),
                    )
                  }
                />
                <TextField
                  name={`memos-attribute-value-${String(row.id)}`}
                  label={t("contracts.drawer.memos.attributeValue", { position: index + 1 })}
                  width="money"
                  value={row.value}
                  onChange={(text) =>
                    setRows((current) =>
                      current.map((item) => (item.id === row.id ? { ...item, value: text } : item)),
                    )
                  }
                />
                <Button
                  variant="ghost"
                  onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}
                >
                  {t("contracts.drawer.memos.removeAttribute")}
                </Button>
              </div>
            ))}
            <div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  setRows((current) => [
                    ...current,
                    { id: Math.max(-1, ...current.map((item) => item.id)) + 1, key: "", value: "" },
                  ])
                }
              >
                {t("contracts.drawer.memos.addAttribute")}
              </Button>
            </div>
          </fieldset>
        ) : null}
        {active.map((dimension, index) => {
          const options: readonly Choice<string>[] = (values[index]?.data ?? [])
            .filter((value) => value.is_active)
            .map((value) => ({ value: value.code, label: `${value.code} · ${value.name}` }));
          return (
            <SelectField
              key={dimension.id}
              name={`memos-dimension-${dimension.code}`}
              label={dimension.name}
              optional
              options={options}
              value={dimensionValues[dimension.code] ?? null}
              onChange={(code) =>
                setDimensionValues((current) => ({ ...current, [dimension.code]: code }))
              }
            />
          );
        })}
        <TextField
          name="memos-comment"
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
      </form>
    </Drawer>
  );
}
