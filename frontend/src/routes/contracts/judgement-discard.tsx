// "Discard" of a draft judgement record (SCREENS §4.1.3, §7.4, §7.6 and §8.3, rev 1.66; PRD SM-10
// `DRAFT` → `VOIDED`; 04 API-R-33 `POST /judgements/{id}/discard`, T-CON-19, E-57 `VOIDED` rev 1.242).
// The Step 1 review, the wizard's judgement drawer and the estimate version drawer create a record
// and send it for review as two requests, and keep the draft only while they stay open: a draft whose
// submission was refused had no command once its drawer was closed, and it holds what waits for the
// contract's records — the activation checklist (PRD IMP-104) and the submission of a modification
// (PRD ERR-95).
//
// And of a rejected record (SCREENS §4.1.3 and §4.9.8, rev 1.74; PRD SM-10 rev 1.199, IMP-145; 04 rev
// 1.296): after a rejection the screens write a new record, and the rejected one kept failing the
// activation checklist with no command on any screen — the discard takes it as it takes a draft.
//
// The API asks `judgement.create` for the record's entity of anyone, not of the creator alone, so the
// command renders for a holder for the contract's contracting entity (the access module; SCREENS §0.6
// SCR-PERM-02 (a)), on a record `discardable` says is one: a draft or a rejected record that is not
// the proposal of a combination group. The discard appends nothing to the contract — a hold that the
// record's earlier submission placed stays and is released on the contract — and the confirmation
// says so where the contract is on hold. A refusal (409: the record is neither a draft nor rejected
// any more, or it is a group's proposal) is shown in the confirmation, and the record stays.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommandKeys } from "../../lib/api/commands";
import type { ApiProblem } from "../../lib/api/problems";
import {
  type Contract,
  type Judgement,
  JUDGEMENT_CREATE_PERMISSION,
  sendCommand,
} from "../../lib/api/queries/contracts";
import { discardable, judgementDiscardPath } from "../../lib/api/queries/judgements";
import type { QueryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";

/** What a discard reads of the record's contract: its entity, its hold and its name. */
export type RecordContract = Pick<Contract, "contracting_entity" | "on_hold" | "external_id">;

/** Whether the viewer is offered "Discard" for a record of the contract. */
export function useRecordDiscard(contract: RecordContract): (record: Judgement) => boolean {
  const access = useAccess();
  const held = access.holds(JUDGEMENT_CREATE_PERMISSION, contract.contracting_entity);
  return (record) => held && discardable(record);
}

export interface DiscardRecordProps {
  readonly record: Judgement;
  readonly contract: RecordContract;
  /** The reads that list the record: read again once it is discarded. */
  readonly invalidates: readonly QueryKey[];
  /** SCREENS SCR-TID-04 `dialog-<name>` of the confirmation. */
  readonly testId: string;
  /** Told once the record is discarded, its reads are read again and the confirmation is closed. */
  readonly onDiscarded?: (() => void) | undefined;
}

/** The command and its confirmation; nothing for a viewer or a record the command is not offered. */
export function DiscardRecord({
  record,
  contract,
  invalidates,
  testId,
  onDiscarded,
}: DiscardRecordProps) {
  const offered = useRecordDiscard(contract)(record);
  const queryClient = useQueryClient();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  // The E-57 status the record had when its confirmation opened; null while it is closed. The
  // confirmation names the record as it was asked about — a rejected record stays "rejected" in its
  // title for the moment in which it has been read again as discarded.
  const [asked, setAsked] = useState<string | null>(null);
  const open = asked !== null;
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  // The confirmation stands until it is closed, also for the moment in which the record it discarded
  // has been read again and is discarded.
  if (!offered && !open) {
    return null;
  }

  const discard = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const outcome = await sendCommand<Judgement>(
        keys,
        "POST",
        judgementDiscardPath(record.id),
        undefined,
      );
      if (!outcome.ok) {
        setProblem(outcome.problem);
        return;
      }
      toast.show({
        tone: "positive",
        message: t("contracts.judgement.discarded", { number: record.judgement_no }),
      });
      // The reads first, the confirmation after: once it closes the record reads as discarded and
      // the command is gone with it, so a second press cannot send a second discard.
      await Promise.all(invalidates.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      setAsked(null);
      onDiscarded?.();
    } catch {
      // No answer: the next press sends the discard under the same key (DG-FE-05).
      noAnswer();
    } finally {
      setBusy(false);
    }
  };

  const consequence = t("contracts.judgement.discard.description", {
    number: record.judgement_no,
  });
  return (
    <>
      <Button
        variant="link"
        onClick={() => {
          setProblem(null);
          setAsked(record.status);
        }}
      >
        {t("contracts.judgement.discard")}
      </Button>
      <Modal
        open={open}
        variant="confirmation"
        title={t(
          asked === "REJECTED"
            ? "contracts.judgement.discard.title.rejected"
            : "contracts.judgement.discard.title",
        )}
        description={
          contract.on_hold
            ? `${consequence} ${t("contracts.judgement.discard.hold", { contract: contract.external_id })}`
            : consequence
        }
        primaryAction={{
          label: t("contracts.judgement.discard"),
          destructive: true,
          onAction: () => void discard(),
        }}
        submitting={busy}
        onClose={() => setAsked(null)}
        testId={testId}
      >
        <RefusalBanner problem={problem} headingLevel={3} />
      </Modal>
    </>
  );
}
