// Record distinct review (SCREENS §4.9.2; 04 §16.1 `POST /contracts/{id}/obligations/{key}/distinct-review`,
// E-105). Conclusion distinct or not distinct (combine with another obligation), basis citing ASC
// 606-10-25-19 or -21, and a rationale; 201 `{judgement_record_id, approval_request_id}`: a
// POB_DISTINCT_OVERRIDE record submitted for review. No `If-Match` (04 §16.1).
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../../components/form/ReasonField";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  type Contract,
  CONTRACT_RECORD_KEYS,
  CONTRACTS_PATH,
} from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { placeProblem } from "../../../lib/api/refusals";
import { t } from "../../../lib/i18n/t";
import { type Choice, RadioGroup, ReadOnlyItem, SelectField } from "./common";

type Conclusion = "distinct" | "nondistinct";
type Basis = "19a" | "19" | "21";

const CODIFICATION: Readonly<Record<Basis, string>> = {
  "19a": "606-10-25-19(a)",
  "19": "606-10-25-19",
  "21": "606-10-25-21",
};

// docs/dev-guide.md DG-FE-06: the fields of the drawer and the members of the body each sends.
const DISTINCT_MEMBERS = {
  conclusion: ["distinctness"],
  integrates: ["integrates_into_obligation_key"],
  basis: ["codification_refs"],
  rationale: ["rationale"],
} as const;
// "Combine with" is on screen for a conclusion of not distinct only.
const DISTINCT_MEMBERS_WITHOUT_INTEGRATES = { ...DISTINCT_MEMBERS, integrates: [] } as const;

export interface DistinctReviewDrawerProps {
  readonly contract: Contract;
  readonly obligation: Obligation;
  readonly obligations: readonly Obligation[];
  readonly onClose: () => void;
}

export function DistinctReviewDrawer({
  contract,
  obligation,
  obligations,
  onClose,
}: DistinctReviewDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const [conclusion, setConclusion] = useState<Conclusion | null>(null);
  const [integrates, setIntegrates] = useState<string | null>(null);
  const [basis, setBasis] = useState<Basis | null>(null);
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contract.id}/obligations/${encodeURIComponent(obligation.obligation_key)}/distinct-review`,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof DISTINCT_MEMBERS>(
        command.problem,
        conclusion === "nondistinct" ? DISTINCT_MEMBERS : DISTINCT_MEMBERS_WITHOUT_INTEGRATES,
      ),
    [command.problem, conclusion],
  );
  const conclusions: readonly Choice<Conclusion>[] = [
    { value: "distinct", label: t("contracts.drawer.distinct.distinct") },
    { value: "nondistinct", label: t("contracts.drawer.distinct.nondistinct") },
  ];
  const bases: readonly Choice<Basis>[] = [
    { value: "19a", label: t("contracts.drawer.distinct.basis.19a") },
    { value: "19", label: t("contracts.drawer.distinct.basis.19") },
    { value: "21", label: t("contracts.drawer.distinct.basis.21") },
  ];
  const others: readonly Choice<string>[] = obligations
    .filter((item) => item.obligation_key !== obligation.obligation_key)
    .map((item) => ({
      value: item.obligation_key,
      label: `${item.obligation_key} · ${item.product.code}`,
    }));

  const submit = async () => {
    setAttempted(true);
    if (
      conclusion === null ||
      basis === null ||
      (conclusion === "nondistinct" && integrates === null) ||
      reasonError(rationale) !== null
    ) {
      return;
    }
    const outcome = await command.submit({
      distinctness: conclusion,
      integrates_into_obligation_key: conclusion === "nondistinct" ? integrates : null,
      codification_refs: [CODIFICATION[basis]],
      rationale: rationale.trim(),
    });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("contracts.drawer.distinct.saved", { key: obligation.obligation_key }),
      });
      onClose();
    }
  };

  const required = t("contracts.drawer.choose");
  return (
    <Drawer
      open
      title={t("contracts.drawer.distinct.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={conclusion !== null || rationale !== ""}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} />}
      primaryAction={{ label: t("contracts.drawer.distinct.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-distinct-review"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <dl className="flex flex-col gap-2">
          <ReadOnlyItem label={t("contracts.drawer.obligation")}>
            <span className="font-mono text-mono">{obligation.obligation_key}</span>
            {` · ${obligation.product.code} · ${obligation.product.name}`}
          </ReadOnlyItem>
        </dl>
        <RadioGroup
          legend={t("contracts.drawer.distinct.conclusion")}
          options={conclusions}
          value={conclusion}
          onChange={setConclusion}
          error={attempted && conclusion === null ? required : placed.fields.conclusion}
        />
        {conclusion === "nondistinct" ? (
          <SelectField
            name="distinct-integrates"
            label={t("contracts.drawer.distinct.combineWith")}
            options={others}
            value={integrates}
            onChange={setIntegrates}
            error={attempted && integrates === null ? required : placed.fields.integrates}
          />
        ) : null}
        <SelectField
          name="distinct-basis"
          label={t("contracts.drawer.distinct.basis.label")}
          options={bases}
          value={basis}
          onChange={setBasis}
          error={attempted && basis === null ? required : placed.fields.basis}
        />
        <ReasonField
          name="distinct-rationale"
          label={t("contracts.drawer.rationale")}
          value={rationale}
          onChange={setRationale}
          showError={attempted}
          error={placed.fields.rationale}
        />
      </form>
    </Drawer>
  );
}
