// A refused command at the fields of its form (DESIGN_SYSTEM DS-CMP-21: server errors map to fields by
// their pointer; 04 API-C-05 `errors[]`). A message is shown where the member it names is entered and
// leaves once that value is edited; what names no field of the form is left for the banner, so that
// "Check the highlighted fields" never stands over a form that highlights nothing (SCREENS_B §9.15
// rev 1.62; SCREENS §11.0 "Refused command", rev 1.31; §10.4 rev 1.35). The banner is `RefusalBanner`
// of src/components/feedback, which takes the placing made here (docs/dev-guide.md DG-FE-06 rev 1.228;
// item KIT-UNPLACED-ERRORS-1).
import { useCallback, useMemo, useState } from "react";

import { ApiProblem } from "./problems";

/** The API member an error names: `scopes[0]` and `policy_values.key` are errors of their member. */
function memberOf(field: string): string {
  return field.split(/[.[]/, 1)[0] ?? field;
}

/**
 * One error at its field: the field shows the first message that names it. A further message is not
 * dropped: unless it says the same sentence it is left for the banner, so that no sentence of a
 * refusal is shown nowhere.
 */
function take<Field extends string>(
  fields: Record<Field, string | null>,
  unplaced: string[],
  field: Field | undefined,
  message: string,
): void {
  if (field !== undefined && fields[field] === null) {
    fields[field] = message;
    return;
  }
  // One sentence is said once, however many members carry it.
  const shown = field !== undefined && fields[field] === message;
  if (!shown && !unplaced.includes(message)) {
    unplaced.push(message);
  }
}

export interface PlacedProblem<Field extends string> {
  /** The first message the problem holds for each field of the form. */
  readonly fields: Readonly<Record<Field, string | null>>;
  /**
   * Messages no field shows, each once; the banner lists them: those that name a member the form has
   * no field for, and a further, different message for a field that already shows one.
   */
  readonly unplaced: readonly string[];
}

/**
 * A problem's errors at the form fields whose API members they name. An error on a member no field
 * sends is left for the banner.
 */
export function placeProblem<Field extends string>(
  problem: ApiProblem | null,
  members: Readonly<Record<Field, readonly string[]>>,
): PlacedProblem<Field> {
  const names = Object.keys(members) as Field[];
  const fields = Object.fromEntries(names.map((name) => [name, null])) as Record<
    Field,
    string | null
  >;
  const unplaced: string[] = [];
  for (const error of problem?.errors ?? []) {
    // A message without a field is the banner's already.
    if (error.field === null) {
      continue;
    }
    const member = memberOf(error.field);
    take(
      fields,
      unplaced,
      names.find((name) => members[name].includes(member)),
      error.message,
    );
  }
  return { fields, unplaced };
}

/**
 * A problem's errors at the form fields whose names end the pointers that name them: `rationale`
 * takes `rationale` and `questionnaire.event_c_met_on` takes that pointer whole. It is the placing of
 * a drawer whose body nests what its fields send, where the first member of a pointer says too
 * little; a form whose fields are the members of the body itself uses `placeProblem`. Each field
 * lists the endings it shows; the first field that takes an error keeps it.
 */
export function placeProblemByEnd<Field extends string>(
  problem: ApiProblem | null,
  endings: Readonly<Record<Field, readonly string[]>>,
): PlacedProblem<Field> {
  const names = Object.keys(endings) as Field[];
  const fields = Object.fromEntries(names.map((name) => [name, null])) as Record<
    Field,
    string | null
  >;
  const unplaced: string[] = [];
  for (const error of problem?.errors ?? []) {
    const pointer = error.field;
    if (pointer === null) {
      continue;
    }
    take(
      fields,
      unplaced,
      names.find((name) => endings[name].some((ending) => pointer.endsWith(ending))),
      error.message,
    );
  }
  return { fields, unplaced };
}

/**
 * The problem as a banner shows it beside the fields: the messages no field shows are listed with
 * those that name no field, each sentence once, and a `detail` that a field shows word for word is
 * not said twice.
 */
export function bannerProblem<Field extends string>(
  problem: ApiProblem,
  placed: PlacedProblem<Field>,
): ApiProblem {
  const shown = Object.values<string | null>(placed.fields);
  const detail = shown.includes(problem.detail) ? null : problem.detail;
  // What the problem already says without a field is not listed a second time — nor is the
  // sentence its detail says: a refusal by name carries its message as the detail too (PRD ERR-92,
  // 409 `invalid-transition` on `status`).
  const said = problem.errors.filter((error) => error.field === null).map((error) => error.message);
  const unplaced = placed.unplaced.filter(
    (message) => !said.includes(message) && message !== detail,
  );
  if (detail === problem.detail && unplaced.length === 0) {
    return problem;
  }
  return new ApiProblem({
    type: problem.type,
    slug: problem.slug,
    title: problem.title,
    status: problem.status,
    detail,
    code: problem.code,
    requestId: problem.requestId,
    errors: [
      ...problem.errors,
      ...unplaced.map((message) => ({
        field: null,
        sheet: null,
        row: null,
        rule_id: null,
        message,
      })),
    ],
  });
}

/**
 * The placing of a screen that itself lists every message of the refusal that names a member, as the
 * findings of a trial balance file by row and column. The banner then says the title, the detail and
 * the messages without a field, and none of the listed ones a second time.
 */
export const LISTED_BY_THE_SCREEN: PlacedProblem<never> = { fields: {}, unplaced: [] };

/** The messages a form's fields show, without the fields that have none. */
export function fieldMessages<Field extends string>(
  fields: Readonly<Record<Field, string | null>>,
): Partial<Record<Field, string>> {
  const shown: Partial<Record<Field, string>> = {};
  for (const name of Object.keys(fields) as Field[]) {
    const message = fields[name];
    if (message !== null) {
      shown[name] = message;
    }
  }
  return shown;
}

export interface FieldRefusals<Field extends string> {
  /** The server's message of each field, until that field is edited. */
  readonly fields: Readonly<Record<Field, string | null>>;
  /** The placing of the problem, for `RefusalBanner`: what the fields took and what they did not. */
  readonly placed: PlacedProblem<Field>;
  /**
   * The problem as the banner shows it (`bannerProblem`); null once every message of the refusal
   * stood at a field and each of those fields has been edited since.
   */
  readonly banner: ApiProblem | null;
  /** The field's value changed: a message describes the value that was sent, so it leaves. */
  readonly edited: (field: Field) => void;
}

/** `placeProblem` for a form: `members` is a constant of the module, one list per field. */
export function useFieldRefusals<Field extends string>(
  problem: ApiProblem | null,
  members: Readonly<Record<Field, readonly string[]>>,
): FieldRefusals<Field> {
  const placed = useMemo(() => placeProblem(problem, members), [problem, members]);
  const [changed, setChanged] = useState<{
    readonly since: ApiProblem | null;
    readonly fields: readonly Field[];
  }>({ since: null, fields: [] });
  const dropped = changed.since === problem ? changed.fields : [];
  const names = Object.keys(placed.fields) as Field[];
  const fields = Object.fromEntries(
    names.map((name) => [name, dropped.includes(name) ? null : placed.fields[name]]),
  ) as Record<Field, string | null>;
  const shown = useMemo(
    () => (problem === null ? null : bannerProblem(problem, placed)),
    [problem, placed],
  );
  // What the banner says beyond its title: without it the banner only points at the fields.
  const says =
    shown !== null && (shown.detail !== null || shown.errors.some((error) => error.field === null));
  const refusedFields = names.filter((name) => placed.fields[name] !== null);
  const settled = refusedFields.length > 0 && refusedFields.every((name) => dropped.includes(name));
  const banner = settled && !says ? null : shown;
  const edited = useCallback(
    (field: Field) => {
      if (placed.fields[field] === null) {
        return;
      }
      setChanged((current) => {
        const before = current.since === problem ? current.fields : [];
        return before.includes(field) ? current : { since: problem, fields: [...before, field] };
      });
    },
    [placed.fields, problem],
  );
  return { fields, placed, banner, edited };
}
