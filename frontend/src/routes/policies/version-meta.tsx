// The effective date of a configuration version on the Policies screens (SCREENS §11.0 "Effective
// date", rev 1.8 and rev 1.31, and "Refused command", rev 1.31; the Meta of §11.1 and §11.2; PRD
// ERR-75; 03 REQ-POL-007; 04 §16.5 "Effective date of a superseding version"; DESIGN_SYSTEM DS-CMP-21,
// DS-I18N-08). How a version's date is entered follows how its kind is chosen: by a contract date (an
// obligation template version; an obligation-assignment or SSP-assignment rule set) or at an instant
// (every other rule set; an accounting policy version). A refused lifecycle command shows the server's
// message on `effective_from` at the Effective from field and lists what no field shows in its banner.
import { type FormEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";

import { Banner } from "../../components/feedback/Banner";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { Field, fieldId } from "../../components/form/Field";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { useCommand } from "../../lib/api/commands";
import { type ApiProblem } from "../../lib/api/problems";
import { type Approval } from "../../lib/api/queries/approvals";
import { type PobTemplateVersionUpdate } from "../../lib/api/queries/pob-templates";
import {
  REVENUE_KINDS,
  type RuleSetKind,
  type RuleSetVersionUpdate,
} from "../../lib/api/queries/rule-sets";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { type QueryKey } from "../../lib/api/query-keys";
import { type PlacedProblem, placeProblem, useFieldRefusals } from "../../lib/api/refusals";
import { effectiveInstant, formatDate, NO_VALUE, timestampDate, utcDateOf } from "../../lib/format";
import { t } from "../../lib/i18n/t";

/**
 * 04 §16.5: `date` — the engine chooses the version by a contract date, so a version that replaces a
 * published one is dated after today; `instant` — the version is read at the instant of a computation
 * or of an act, so it takes effect at its publication or at a later instant.
 */
export type EffectiveForm = "date" | "instant";

export function ruleSetForm(kind: RuleSetKind): EffectiveForm {
  return REVENUE_KINDS.includes(kind) ? "date" : "instant";
}

/** The name of the Effective from field in every version editor, the API member it sends. */
export const EFFECTIVE_FIELD = "effective_from";

/** Moves focus to the Effective from field: a refusal of the date is answered there (DS-CMP-21). */
export function focusEffectiveFrom(): void {
  document.getElementById(fieldId(EFFECTIVE_FIELD))?.focus();
}

/** The approvers who decided the version's approval request, in step order, each once. */
export function approverNames(approval: Approval | undefined): readonly string[] {
  const names: string[] = [];
  for (const step of approval?.steps ?? []) {
    for (const decision of step.decisions) {
      if (!names.includes(decision.approver.display_name)) {
        names.push(decision.approver.display_name);
      }
    }
  }
  return names;
}

interface Dated {
  readonly effective_from: string | null;
  readonly published_at: string | null;
}

/**
 * The UTC date a version takes or took effect (SCREENS §11.0): that of its effective instant, or, for a
 * version read at an instant and published without one, that of its publication. Null while unknown.
 */
export function effectiveDate(version: Dated, form: EffectiveForm): string | null {
  if (version.effective_from !== null) {
    return timestampDate(version.effective_from);
  }
  return form === "instant" && version.published_at !== null
    ? timestampDate(version.published_at)
    : null;
}

/** The "Published" caption of the lifecycle stepper: "Effective <date>" or "Effective on approval". */
export function effectiveCaption(version: Dated, form: EffectiveForm): string | undefined {
  const date = effectiveDate(version, form);
  if (date !== null) {
    return t("policies.lifecycle.effective", { date: formatDate(date) });
  }
  return form === "instant" ? t("policies.lifecycle.effectiveOnApproval") : undefined;
}

const EFFECTIVE_MEMBERS = { effective: [EFFECTIVE_FIELD] } as const;
const NO_MEMBERS = {} as const;

/** Whether a refusal names the effective date, the field a version editor answers it at. */
export function refusesEffectiveDate(problem: ApiProblem): boolean {
  return placeProblem(problem, EFFECTIVE_MEMBERS).fields.effective !== null;
}

export interface LifecycleRefusal {
  /** The server's message on the effective date, until the date is edited. */
  readonly effective: string | null;
  readonly effectiveEdited: () => void;
  /** The refusal as the header banner shows it, or null. */
  readonly banner: ApiProblem | null;
  /** The placing of that refusal, for `RefusalBanner`: what the date field took of it. */
  readonly placed: PlacedProblem<string>;
}

/**
 * SCREENS §11.0 "Refused command" (rev 1.31). `dated` is the refusal of the commands that check the
 * effective date ("Submit for approval"; a save of the version), `other` that of the remaining
 * lifecycle commands. A message on `effective_from` goes to the field; every other message of
 * `errors[]` is listed in the banner, with the problem's detail unless the field says the same.
 */
export function useLifecycleRefusal(
  dated: ApiProblem | null,
  other: ApiProblem | null,
): LifecycleRefusal {
  const first = useFieldRefusals(dated, EFFECTIVE_MEMBERS);
  const second = useFieldRefusals(other, NO_MEMBERS);
  const { edited } = first;
  return {
    effective: first.fields.effective,
    effectiveEdited: () => {
      edited("effective");
    },
    banner: first.banner ?? second.banner,
    placed: first.banner !== null ? first.placed : second.placed,
  };
}

export interface SubmissionOrder {
  /** "Submit for approval" is sent. */
  readonly submitted: () => void;
  /**
   * A command that changes what a submission is decided on is sent: "Run tests", a save. What it
   * returns is called at that command's success and clears the refusal of a submission sent before it.
   */
  readonly changing: () => () => void;
}

/**
 * SCREENS §11.0 "Refused command": a successful "Run tests" and a saved effective date clear the
 * refusal of an earlier submission, and of no other. A command's success is known only after the reads
 * it causes have come back, and "Submit for approval" can be sent meanwhile: that submission was
 * decided on the version after the command, so its answer stays (POLICY-VERSION-RESET-RACE-1).
 * `reset` is that of the submit command.
 */
export function useSubmissionOrder(reset: () => void): SubmissionOrder {
  const sent = useRef(0);
  return useMemo(
    () => ({
      submitted: () => {
        sent.current += 1;
      },
      changing: () => {
        const before = sent.current;
        return () => {
          if (sent.current === before) {
            reset();
          }
        };
      },
    }),
    [reset],
  );
}

/** What the Meta reads of a version of either kind (04 SC-V). */
export interface MetaVersion extends Dated {
  readonly effective_to: string | null;
  readonly content_sha256: string | null;
  readonly row_version: number;
}

type EffectiveUpdate = Pick<RuleSetVersionUpdate, "effective_from"> &
  Pick<PobTemplateVersionUpdate, "effective_from">;

export interface VersionMetaProps {
  readonly version: MetaVersion;
  /** The `PATCH` path of the version; the Meta sends `effective_from` with `If-Match`. */
  readonly path: string;
  readonly form: EffectiveForm;
  /** The version replaces a published version of its scope (PRD ERR-75). */
  readonly supersedes: boolean;
  /** The date is needed before submission; an optional date may be cleared. */
  readonly required: boolean;
  readonly approval: Approval | undefined;
  readonly editable: boolean;
  readonly invalidates: readonly QueryKey[];
  /** The refusal of the date by a lifecycle command (`useLifecycleRefusal`). */
  readonly refusal: string | null;
  readonly onEdited: () => void;
  /**
   * "Save effective date" is sent; what this returns is called once the date was saved, when what a
   * submission before the save was refused for no longer holds (`SubmissionOrder.changing`).
   */
  readonly onSave?: (() => () => void) | undefined;
  readonly className?: string | undefined;
}

function helpOf(form: EffectiveForm, supersedes: boolean): string {
  if (form === "instant") {
    return t("policies.meta.effectiveHelp.instant");
  }
  return t(
    supersedes ? "policies.meta.effectiveHelp.dateSupersedes" : "policies.meta.effectiveHelp.date",
  );
}

/** SCREENS §11.1 and §11.2 Meta: a form while DRAFT or TESTED for authors; a definition list otherwise. */
export function VersionMeta({
  version,
  path,
  form,
  supersedes,
  required,
  approval,
  editable,
  invalidates,
  refusal,
  onEdited,
  onSave,
  className,
}: VersionMetaProps) {
  const toast = useToast();
  const formId = useId();
  const initial = version.effective_from === null ? "" : timestampDate(version.effective_from);
  const [typed, setTyped] = useState(initial === "" ? "" : formatDate(initial));
  const [date, setDate] = useState<string | null>(initial === "" ? null : initial);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const patch = useCommand<MetaVersion>({ method: "PATCH", path, invalidates });
  const approvers = approverNames(approval);
  const shown = effectiveDate(version, form);
  const items: { readonly label: string; readonly value: ReactNode; readonly help?: string }[] = [
    {
      label: t("policies.meta.effectiveTo"),
      value: (
        <span className="num">
          {formatDate(version.effective_to === null ? null : timestampDate(version.effective_to))}
        </span>
      ),
      help: t("policies.meta.effectiveToHelp"),
    },
    { label: t("policies.meta.author"), value: approval?.preparer.display_name ?? NO_VALUE },
    {
      label: t("policies.meta.approver"),
      value: approvers.length === 0 ? NO_VALUE : approvers.join(", "),
    },
    {
      label: t("policies.meta.sha"),
      value:
        version.content_sha256 === null ? (
          NO_VALUE
        ) : (
          <span className="break-all font-mono text-mono-sm">{version.content_sha256}</span>
        ),
    },
  ];
  const list = (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-body-sm">
      {editable ? null : (
        <>
          <dt className="text-fg-3">{t("policies.meta.effectiveFrom")}</dt>
          <dd className="num text-fg-1">
            {shown !== null
              ? formatDate(shown)
              : form === "instant"
                ? t("policies.meta.onApproval")
                : NO_VALUE}
          </dd>
        </>
      )}
      {items.map((item) => (
        <div key={item.label} className="contents">
          <dt className="text-fg-3">{item.label}</dt>
          <dd className="text-fg-1">
            {item.value}
            {item.help === undefined ? null : (
              <span className="block text-caption text-fg-3">{item.help}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
  if (!editable) {
    return (
      <section aria-label={t("policies.meta.label")} className={className}>
        {list}
      </section>
    );
  }
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (patch.pending || formatError !== null) {
      return;
    }
    if (date === null && required) {
      setMissing(true);
      focusEffectiveFrom();
      return;
    }
    // A version read at an instant and dated today takes effect when it is approved: 12:00 UTC of
    // today has passed, or passes before the approval, and the server refuses a past instant.
    const sent =
      date === null || (form === "instant" && date === utcDateOf(Date.now()))
        ? null
        : effectiveInstant(date);
    const saved = onSave?.();
    const outcome = await patch.submit({ effective_from: sent } satisfies EffectiveUpdate, {
      ifMatch: rowIfMatch(version.row_version),
    });
    if (outcome.kind === "succeeded") {
      if (sent === null) {
        // The field shows what is stored: no date.
        setTyped("");
        setDate(null);
      }
      saved?.();
      toast.show({
        tone: "positive",
        message: t(
          sent === null && form === "instant"
            ? "policies.meta.savedOnApproval"
            : "policies.meta.saved",
        ),
      });
    }
  };
  const error =
    formatError ??
    (missing ? t("policies.meta.effectiveMissing") : null) ??
    patch.fieldErrors[EFFECTIVE_FIELD] ??
    refusal;
  return (
    <section aria-label={t("policies.meta.label")} className={cn("flex flex-col gap-4", className)}>
      <form
        id={formId}
        aria-label={t("policies.meta.form")}
        noValidate
        onSubmit={(event) => void save(event)}
      >
        {/* The date keeps its DS-CMP-21 width; the message and the help line take the text width. */}
        <Field
          name={EFFECTIVE_FIELD}
          label={t("policies.meta.effectiveFrom")}
          required={required}
          optional={!required}
          help={helpOf(form, supersedes)}
          error={error}
          width="text"
        >
          {(control) => (
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-40">
                <DateInput
                  control={control}
                  value={typed}
                  onChange={(text) => {
                    // A blur echoes the date as it reads; only another text is an edit.
                    if (text !== typed) {
                      setMissing(false);
                      onEdited();
                    }
                    setTyped(text);
                  }}
                  onValue={setDate}
                  onFormatError={setFormatError}
                  invalid={error !== null}
                />
              </div>
              <Button variant="secondary" type="submit" loading={patch.pending}>
                {t("policies.meta.save")}
              </Button>
            </div>
          )}
        </Field>
      </form>
      {patch.banner === null ? null : <Banner tone="warning" title={patch.banner} />}
      {list}
    </section>
  );
}
