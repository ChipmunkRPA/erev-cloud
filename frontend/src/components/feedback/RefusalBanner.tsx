// RefusalBanner (DESIGN_SYSTEM DS-CMP-29; docs/dev-guide.md DG-FE-06 rev 1.228; SCREENS §0.7 rev 1.47;
// item KIT-UNPLACED-ERRORS-1): the one way a form shows a refused command. It says the problem's title
// and detail and every sentence of `errors[]`, each once. A form whose fields show messages hands it
// their placing (`placeProblem` or `useFieldRefusals` of src/lib/api/refusals.ts) and the banner then
// lists only what no field took; a form that hands it none is shown every sentence, so that a refusal
// is never shown nowhere. A record that changed under the member (412) is said in its place. A form
// that knows the way out of a refusal hands the banner its action (SCREENS §4.9.1 rev 1.72), shown
// under the sentences of the problem and never beside the line of a 412.
import type { ReactNode } from "react";

import type { ApiProblem } from "../../lib/api/problems";
import { bannerProblem, type PlacedProblem } from "../../lib/api/refusals";
import { t } from "../../lib/i18n/t";
import { Banner } from "./Banner";

export interface RefusalBannerProps {
  readonly problem: ApiProblem | null;
  /** What the fields of the form show of the problem; without it every sentence is the banner's. */
  readonly placed?: PlacedProblem<string> | undefined;
  /** SCREENS SCR-ST-09: the line of `useCommand().banner` after a 412. */
  readonly conflict?: string | null | undefined;
  /** A screen's own sentence for the problem's slug, in place of the problem's title. */
  readonly title?: string | undefined;
  /** Link-button actions for the problem shown, for example the command that leads out of it. */
  readonly actions?: ReactNode;
  readonly headingLevel?: 2 | 3 | 4 | undefined;
}

/**
 * What the banner says beyond the title: the detail, unless a field shows it word for word, and the
 * sentences of `errors[]` no field shows, each once and never the detail again.
 */
export function refusalLines(
  problem: ApiProblem,
  placed?: PlacedProblem<string>,
): { readonly detail: string | null; readonly sentences: readonly string[] } {
  const shown = placed === undefined ? problem : bannerProblem(problem, placed);
  const sentences: string[] = [];
  for (const error of shown.errors) {
    const listed = placed === undefined || error.field === null;
    if (
      listed &&
      error.message !== "" &&
      error.message !== shown.detail &&
      !sentences.includes(error.message)
    ) {
      sentences.push(error.message);
    }
  }
  return { detail: shown.detail, sentences };
}

export function RefusalBanner({
  problem,
  placed,
  conflict = null,
  title,
  actions,
  headingLevel,
}: RefusalBannerProps) {
  if (conflict !== null) {
    return <Banner tone="warning" title={conflict} headingLevel={headingLevel ?? 2} />;
  }
  if (problem === null) {
    return null;
  }
  const { detail, sentences } = refusalLines(problem, placed);
  return (
    <Banner
      tone="negative"
      title={title ?? problem.title}
      announce="live"
      headingLevel={headingLevel ?? 2}
      actions={actions}
    >
      {detail === null ? null : <p>{detail}</p>}
      {sentences.map((sentence) => (
        <p key={sentence}>{sentence}</p>
      ))}
      {problem.requestId === null ? null : (
        <p>{t("common.refusal.reference", { reference: problem.requestId })}</p>
      )}
    </Banner>
  );
}
