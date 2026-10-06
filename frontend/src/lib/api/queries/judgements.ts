// Judgement records beside their reads (04 API-R-33, T-CON-19, E-57 rev 1.242; PRD SM-10; SCREENS
// §0.8, rev 1.66): what every screen that names a record asks of it — the word of its status, whether
// it stands, whether it is a record a screen discards — and the path of the discard.
import { hasMessage, t } from "../../i18n/t";
import { type Judgement, JUDGEMENTS_PATH } from "./contracts";

/**
 * E-57 status of a judgement record in words (SCREENS §0.8, rev 1.66): the one reading of the
 * workbench's Step 1 evidence, the assessment drawer, the approval request, the modification wizard
 * and the estimate screens. A record sent for review reads "Waiting for review" — "Submitted" names
 * the preparer's act, the state is a wait — and a discarded draft "Void", as a discarded estimate
 * version and modification read. The literal stands where the catalogue holds no word, so a status a
 * later API adds reads as itself instead of failing the screen.
 */
export function judgementStatusLabel(status: string): string {
  const key = `contracts.workbench.step1.status.${status}`;
  return hasMessage(key) ? t(key) : status;
}

/**
 * Whether a record under E-57 `status` stands for what names it — the `CONSTRAINT` record of a
 * variable-consideration version at its submission (04 §16.14 rev 1.241; PRD IMP-140), the override
 * record of a modification's departing treatment (SCREENS §7.6): sent for review or reviewed. Every
 * other status does not — a draft, a rejected, superseded or discarded record, and a literal this
 * build does not know.
 */
export function recordStands(status: string): boolean {
  return status === "SUBMITTED" || status === "REVIEWED";
}

/** 04 T-CON-19: the draft record a `PROPOSED` combination group is submitted with. */
const GROUP_SUBJECT = "combination_group";

/**
 * E-57 statuses the discard takes (PRD SM-10 rev 1.199; 04 rev 1.296): a draft, and a rejected
 * record — a reviewer's No that nobody answered, which fails the activation checklist until it is
 * discarded (PRD IMP-145).
 */
const DISCARDED_FROM: ReadonlySet<string> = new Set(["DRAFT", "REJECTED"]);

/**
 * A record a screen offers to discard (`POST /judgements/{id}/discard`, PRD SM-10 `DRAFT` → `VOIDED`
 * and, rev 1.199, `REJECTED` → `VOIDED`). The API takes any draft and any rejected record but the
 * proposal of a combination group — a record of topic `COMBINATION` whose subject is the group —
 * which is decided with its group (409): the screen knows it by those two members and does not offer
 * the command; the 409 stays the guarantee.
 */
export function discardable(record: Pick<Judgement, "status" | "topic" | "subject_type">): boolean {
  return (
    DISCARDED_FROM.has(record.status) &&
    !(record.topic === "COMBINATION" && record.subject_type === GROUP_SUBJECT)
  );
}

/** `POST /judgements/{id}/discard`, without a body. */
export function judgementDiscardPath(judgementId: string): string {
  return `${JUDGEMENTS_PATH}/${judgementId}/discard`;
}
