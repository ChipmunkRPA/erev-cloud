import { useId, useMemo, useState } from "react";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { Field } from "../../../components/form/Field";
import { MultiSelect } from "../../../components/form/MultiSelect";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  CONTRACTS_PATH,
  CONTRACT_RECORD_KEYS,
  type Contract,
} from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { placeProblem } from "../../../lib/api/refusals";
import { t } from "../../../lib/i18n/t";
import { TextField } from "./common";

const MEMBERS = { lines: ["obligation_keys"], comment: ["comment"] } as const;

export function RegroupDrawer({
  contract,
  obligations,
  onClose,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
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
    contract.status === "DRAFT" &&
    selected.length > 0 &&
    comment.trim() !== "" &&
    selected.every((key) => options.some((option) => option.value === key));
  const submit = async () => {
    setAttempted(true);
    if (!valid || command.pending) return;
    const outcome = await command.submit({ obligation_keys: selected, comment: comment.trim() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("contracts.drawer.regroup.saved") });
      onClose();
    }
  };
  return (
    <Drawer
      open
      title={t("contracts.drawer.regroup.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={selected.length > 0 || comment !== ""}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={{ label: t("contracts.drawer.regroup.move"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <p>{t("contracts.drawer.regroup.help")}</p>
        <fieldset
          disabled={command.pending || contract.status !== "DRAFT"}
          className="flex flex-col gap-4"
        >
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
    </Drawer>
  );
}
