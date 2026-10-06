// Apply hold (SCREENS §4.9.4; 04 §16.1 `POST /contracts/{id}/apply-hold`; BR-PLT-08): level contract or
// one obligation, hold type recognition or journal export, and a reason of at least 10 characters,
// with `If-Match`.
//
// Release hold (SCREENS §4.9.4 rev 1.75; 04 §16.1 `POST /contracts/{id}/release-hold`, §16.1 and §16.2
// rev 1.299 `holds`; T-CON-20): the open holds of the contract and of its obligations, the ones that
// are released by hand in a select and the others with the API's sentence for why not, and a comment
// of at least 10 characters, with `If-Match`. Until 04 rev 1.299 no read answered the id the command
// takes, and a hold applied on a screen had no exit on the screens (L5-4-Q-30).
import { useId, useMemo, useState } from "react";

import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { useToast } from "../../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../../components/form/ReasonField";
import { Drawer } from "../../../components/ui/Drawer";
import { useCommand } from "../../../lib/api/commands";
import {
  type Contract,
  contractIfMatch,
  CONTRACT_RECORD_KEYS,
  CONTRACTS_PATH,
  type HoldType,
} from "../../../lib/api/queries/contracts";
import { type Obligation, type OpenHold, openHolds } from "../../../lib/api/queries/obligations";
import { placeProblem } from "../../../lib/api/refusals";
import { formatTimestamp } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { type Choice, RadioGroup, SelectField } from "./common";

type Level = "CONTRACT" | "OBLIGATION";

// docs/dev-guide.md DG-FE-06: the fields of the drawer and the members of the body each sends.
const HOLD_MEMBERS = { obligation: ["obligation_key"], reason: ["reason"] } as const;
// At contract level no obligation is on screen: an error on that member is the banner's.
const HOLD_MEMBERS_OF_CONTRACT = { obligation: [], reason: ["reason"] } as const;

export interface ApplyHoldDrawerProps {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  /** The obligation of the pane, preselected at obligation level. */
  readonly obligationKey?: string | undefined;
  readonly onClose: () => void;
}

export function ApplyHoldDrawer({
  contract,
  obligations,
  obligationKey,
  onClose,
}: ApplyHoldDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const [level, setLevel] = useState<Level>(
    obligationKey === undefined ? "CONTRACT" : "OBLIGATION",
  );
  const [key, setKey] = useState<string | null>(obligationKey ?? null);
  const [holdType, setHoldType] = useState<HoldType>("recognition");
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contract.id}/apply-hold`,
    ifMatch: contractIfMatch(contract.head_stream_version),
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(
    () =>
      placeProblem<keyof typeof HOLD_MEMBERS>(
        command.problem,
        level === "OBLIGATION" ? HOLD_MEMBERS : HOLD_MEMBERS_OF_CONTRACT,
      ),
    [command.problem, level],
  );
  const levels: readonly Choice<Level>[] = [
    { value: "CONTRACT", label: t("contracts.drawer.level.contract") },
    { value: "OBLIGATION", label: t("contracts.drawer.level.obligation") },
  ];
  const types: readonly Choice<HoldType>[] = [
    { value: "recognition", label: t("contracts.list.hold.recognition") },
    { value: "journal_export", label: t("contracts.list.hold.journalExport") },
  ];
  const keys: readonly Choice<string>[] = obligations.map((item) => ({
    value: item.obligation_key,
    label: `${item.obligation_key} · ${item.product.name}`,
  }));

  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null || (level === "OBLIGATION" && key === null)) {
      return;
    }
    const outcome = await command.submit({
      hold_type: holdType,
      obligation_key: level === "OBLIGATION" ? key : null,
      reason: reason.trim(),
    });
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({
        tone: "positive",
        message: t("contracts.drawer.hold.applied", { contract: contract.external_id }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("contracts.list.bulk.hold")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={reason !== ""}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={{ label: t("contracts.list.bulk.hold"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-apply-hold"
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
            name="hold-obligation"
            label={t("contracts.drawer.obligation")}
            options={keys}
            value={key}
            onChange={setKey}
            error={
              attempted && key === null ? t("contracts.drawer.choose") : placed.fields.obligation
            }
          />
        ) : null}
        <RadioGroup
          legend={t("contracts.list.hold.type")}
          options={types}
          value={holdType}
          onChange={setHoldType}
        />
        <ReasonField
          name="hold-reason"
          label={t("contracts.list.hold.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
          error={placed.fields.reason}
        />
      </form>
    </Drawer>
  );
}

// docs/dev-guide.md DG-FE-06: the fields of the release and the member of the body each sends.
const RELEASE_MEMBERS = { hold: ["hold_id"], comment: ["comment"] } as const;

/**
 * A hold in words: "<type label> · <reason> · applied <timestamp>", the hold of one obligation with
 * its key in front (SCREENS §4.9.4 rev 1.75). The read answers the instant the hold was applied and
 * no date of the entity, so the label names the instant (DS-FMT-17).
 */
function holdLabel({ hold, obligationKey }: OpenHold): string {
  const words = {
    type: t(`contracts.history.hold.${hold.hold_type}`),
    reason: hold.reason,
    at: formatTimestamp(hold.applied_at),
  };
  return obligationKey === null
    ? t("contracts.drawer.release.option", words)
    : t("contracts.drawer.release.optionOf", { ...words, key: obligationKey });
}

export interface ReleaseHoldDrawerProps {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  /** The hold the obligation pane named: chosen when the drawer opens. */
  readonly holdId?: string | undefined;
  readonly onClose: () => void;
}

export function ReleaseHoldDrawer({
  contract,
  obligations,
  holdId,
  onClose,
}: ReleaseHoldDrawerProps) {
  const formId = useId();
  const keptId = useId();
  const toast = useToast();
  const [picked, setPicked] = useState<string | null>(holdId ?? null);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contract.id}/release-hold`,
    ifMatch: contractIfMatch(contract.head_stream_version),
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const placed = useMemo(
    () => placeProblem<keyof typeof RELEASE_MEMBERS>(command.problem, RELEASE_MEMBERS),
    [command.problem],
  );
  // 04 §16.1 rev 1.299: `release_refusal` is the sentence the command would answer for the hold as
  // it stands, or null where it would take it. The screen keeps no rule of its own: a hold with a
  // sentence is no option and is listed with it; the command's 409 stays the backstop.
  const holds = openHolds(contract, obligations);
  const byHand = holds.filter((item) => item.hold.release_refusal === null);
  const kept = holds.filter((item) => item.hold.release_refusal !== null);
  // One hold alone is chosen at once. A hold that is no option any more — released meanwhile, or
  // one the API now refuses — is no choice.
  const only = byHand.length === 1 ? byHand[0] : undefined;
  const chosen =
    only !== undefined
      ? only.hold.id
      : byHand.some((item) => item.hold.id === picked)
        ? picked
        : null;

  const submit = async () => {
    setAttempted(true);
    if (chosen === null || reasonError(comment) !== null) {
      return;
    }
    const outcome = await command.submit({ hold_id: chosen, comment: comment.trim() });
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({
        tone: "positive",
        message: t("contracts.drawer.release.released", { contract: contract.external_id }),
      });
      onClose();
    }
  };

  return (
    <Drawer
      open
      title={t("contracts.drawer.release.title")}
      subtitle={contract.external_id}
      initialFocus="field"
      dirty={comment !== ""}
      submitting={command.pending}
      banner={<RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />}
      primaryAction={
        byHand.length === 0
          ? undefined
          : { label: t("contracts.drawer.release.title"), form: formId }
      }
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-03-drawer-release-hold"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {byHand.length === 0 ? null : (
          <>
            <SelectField
              name="release-hold"
              label={t("contracts.drawer.release.hold")}
              options={byHand.map((item) => ({ value: item.hold.id, label: holdLabel(item) }))}
              value={chosen}
              onChange={setPicked}
              error={
                attempted && chosen === null ? t("contracts.drawer.choose") : placed.fields.hold
              }
            />
            <ReasonField
              name="release-comment"
              label={t("contracts.drawer.release.comment")}
              value={comment}
              onChange={setComment}
              showError={attempted}
              error={placed.fields.comment}
            />
          </>
        )}
        {kept.length === 0 ? null : (
          <div className="flex flex-col gap-1">
            <p id={keptId} className="text-body-sm font-semibold text-fg-1">
              {t("contracts.drawer.release.notByHand")}
            </p>
            <ul aria-labelledby={keptId} className="flex flex-col gap-2 text-body-sm">
              {kept.map((item) => (
                <li key={item.hold.id} className="flex flex-col">
                  <span className="text-fg-1">{holdLabel(item)}</span>
                  <span className="text-fg-2">{item.hold.release_refusal}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </Drawer>
  );
}
