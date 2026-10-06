// The API's rule of an as-locked report run, for the fakes of the screens' tests (item
// RV-AS-LOCKED-DEFAULT-1; SCREENS_B RV-04 rev 1.98; ENGINE_SPEC_B S15-R-19; docs/dev-guide.md DG-FE-18).
// `as-locked.json` is written by `scripts/as_locked_fixture.py` from `locked.reconcile_selectors` and
// the report catalogue: every definition as the route answers it, the keys an as-locked run admits,
// the refusals' sentences, and a table of parameter sets with the function's own findings.
// `asLockedFindings` is that rule in TypeScript, and `as-locked.test.ts` holds it to every row of the
// table — a fake that answered 202 to any set let three views send what the API refuses. A fake of
// `POST /report-runs` asks `asLockedRefusal` before it answers.
//
// S15-R-19 rev 1.167 (register index 280; SCREENS_B RV-04 rev 1.101): a run names a LOCK record or is
// refused — a REOPEN or a PERMANENT_LOCK record froze no dataset. `notALock` is `locked.not_a_lock`,
// held to every row of the fixture's `records`.
import type { ReportDefinition } from "../lib/api/queries/reports";

import fixture from "./as-locked.json";
import { problemResponse } from "./msw";

/** One element of a problem's `errors` (04 API-C-05). */
export interface Finding {
  readonly field: string;
  readonly rule_id: string | null;
  readonly message: string;
}

/**
 * A lock record of the fake's world: one entity, one book, one period (04 T-CLS-04). `kind` is E-63
 * `lock_kind` as API-S-Period states it — LOCK, REOPEN, PERMANENT_LOCK — and only a LOCK froze
 * datasets (T-CLS-05); a record that says none is the record of a close, a LOCK. For another record
 * `dataset_lock_id` is the LOCK whose datasets stand for its period (API-S-Period `dataset_lock`);
 * absent or null where none does.
 */
export interface LockScope {
  readonly id: string;
  readonly entity_code: string;
  readonly book_code: string;
  readonly period_key: string;
  readonly kind?: string;
  readonly dataset_lock_id?: string | null;
}

/** A row of `records`: a record a run can name, and what `locked.not_a_lock` answers for it. */
interface RecordRow {
  readonly kind: string;
  readonly id: string;
  readonly period_key: string;
  readonly dataset_lock_id: string | null;
  readonly refusal: string | null;
}

interface AsLockedCase {
  readonly report: string;
  readonly case: string;
  readonly given: Readonly<Record<string, unknown>>;
  readonly findings: readonly Finding[];
}

interface AsLockedFixture {
  readonly rule_id: string;
  readonly scope_rule_id: string;
  readonly field: string;
  readonly admitted_keys: readonly string[];
  readonly period_keys: readonly string[];
  readonly messages: Readonly<
    Record<
      | "not_a_lock_selector"
      | "entity_mismatch"
      | "book_mismatch"
      | "period_mismatch"
      | "no_dataset"
      | "lock_unknown"
      | "not_a_lock"
      | "pass_dataset_lock"
      | "no_dataset_lock",
      string
    >
  >;
  /** What the API calls a record that is no LOCK, by kind: "a reopen record", "the permanent lock". */
  readonly record_words: Readonly<Record<string, string>>;
  /** The reports with a lock dataset, by code, with the E-64 kind. */
  readonly kinds: Readonly<Record<string, string>>;
  /** The lock the table's findings are given for. */
  readonly lock: LockScope;
  readonly records: readonly RecordRow[];
  readonly definitions: readonly ReportDefinition[];
  readonly cases: readonly AsLockedCase[];
}

export const AS_LOCKED = fixture as unknown as AsLockedFixture;

const LOCK_KEY = "period_lock_id";
const PARAMETERS = "parameters.";

/** The definition of the report as `GET /report-definitions/{code}` answers it. */
export function definitionOf(code: string): ReportDefinition {
  const found = AS_LOCKED.definitions.find((definition) => definition.code === code);
  if (found === undefined) {
    throw new Error(`The catalogue holds no report ${code}`);
  }
  return found;
}

/** True for a report whose parameter schema has the key. */
export function takes(definition: ReportDefinition, key: string): boolean {
  const properties = definition.parameters_schema.properties;
  return typeof properties === "object" && properties !== null && Object.hasOwn(properties, key);
}

/**
 * A sentence of the API from its template, as `str.format` writes it: `{name}` is the value, and a
 * doubled brace is the brace itself ("GET /periods/{{id}}/locks").
 */
function said(template: string, values: Readonly<Record<string, string>>): string {
  return template.replace(/\{\{|\}\}|\{([a-z_]+)\}/g, (whole, name: string | undefined) => {
    if (name === undefined) {
      return whole.charAt(0);
    }
    return values[name] ?? whole;
  });
}

/**
 * `locked.not_a_lock`: the refusal of a run that names the record, null for a LOCK. The record, what
 * it is and its period; then the LOCK whose datasets stand for the period or, where none stands, what
 * the caller can do instead.
 */
export function notALock(record: LockScope): string | null {
  const kind = record.kind ?? "LOCK";
  if (kind === "LOCK") {
    return null;
  }
  const { messages } = AS_LOCKED;
  const period = record.period_key;
  const named = said(messages.not_a_lock, {
    lock: record.id,
    record: AS_LOCKED.record_words[kind] ?? kind,
    period,
    kind,
  });
  const standing = record.dataset_lock_id ?? null;
  return standing === null
    ? `${named} ${said(messages.no_dataset_lock, { period })}`
    : `${named} ${said(messages.pass_dataset_lock, { period, dataset_lock: standing })}`;
}

/**
 * The findings of the API against the parameters of an as-locked run, in `framework._resolve`'s
 * order: a report without a lock dataset; a record that is no LOCK; else
 * `locked.reconcile_selectors` — no parameter but the lock, a cutoff and the lock's own entity, book
 * and period.
 */
export function asLockedFindings(
  code: string,
  given: Readonly<Record<string, unknown>>,
  lock: LockScope,
): Finding[] {
  const { messages, rule_id: rule } = AS_LOCKED;
  const kind = AS_LOCKED.kinds[code];
  if (kind === undefined) {
    return [
      { field: AS_LOCKED.field, rule_id: rule, message: said(messages.no_dataset, { code }) },
    ];
  }
  const frozeNothing = notALock(lock);
  if (frozeNothing !== null) {
    return [{ field: AS_LOCKED.field, rule_id: rule, message: frozeNothing }];
  }
  const findings: Finding[] = [];
  const refuse = (key: string, message: string) => {
    findings.push({ field: `${PARAMETERS}${key}`, rule_id: rule, message });
  };
  for (const key of Object.keys(given).sort()) {
    if (!AS_LOCKED.admitted_keys.includes(key)) {
      refuse(key, said(messages.not_a_lock_selector, { key, kind, lock: lock.id }));
    }
  }
  if (Object.hasOwn(given, "entity_codes")) {
    const codes = Array.isArray(given.entity_codes) ? given.entity_codes.map(String) : [];
    if (codes.length !== 1 || codes[0] !== lock.entity_code) {
      refuse(
        "entity_codes",
        said(messages.entity_mismatch, { entity: lock.entity_code, lock: lock.id }),
      );
    }
  }
  if (Object.hasOwn(given, "book") && String(given.book) !== lock.book_code) {
    refuse("book", said(messages.book_mismatch, { book: lock.book_code, lock: lock.id }));
  }
  for (const key of AS_LOCKED.period_keys) {
    if (Object.hasOwn(given, key) && String(given[key]) !== lock.period_key) {
      refuse(key, said(messages.period_mismatch, { key, period: lock.period_key, lock: lock.id }));
    }
  }
  return findings;
}

/**
 * The API's answer to a creation that names a lock, where it is a refusal: 422 with the findings, as
 * `framework._invalid` words it. Null for a creation that names no lock, and for one the rule admits —
 * the fake then answers as it would have. `locks` are the locks of the fake's world; another id is no
 * lock of the workspace.
 */
export function asLockedRefusal(
  code: string,
  parameters: Readonly<Record<string, unknown>>,
  locks: readonly LockScope[],
): Response | null {
  const id = parameters[LOCK_KEY];
  if (id === undefined || id === null) {
    return null;
  }
  const lock = locks.find((item) => item.id === id);
  const findings =
    lock === undefined
      ? [
          {
            field: AS_LOCKED.field,
            rule_id: AS_LOCKED.scope_rule_id,
            message: AS_LOCKED.messages.lock_unknown,
          },
        ]
      : asLockedFindings(code, parameters, lock);
  return findings.length === 0 ? null : invalid(findings);
}

/** 422 `validation-failed` with the findings, as `framework._invalid` words it. */
function invalid(findings: readonly Finding[]): Response {
  return problemResponse("validation-failed", 422, "Check the highlighted fields", {
    detail:
      findings.length === 1
        ? "1 field needs attention."
        : `${String(findings.length)} fields need attention.`,
    errors: findings.map((finding) => ({ ...finding })),
  });
}

/**
 * The API's answer to the rerun of a stored run that names the record, where it is this refusal
 * (`framework.rerun`, S15-R-19 rev 1.167): a run stored before the revision may name a record that
 * froze nothing, and its rerun is refused as its creation is. Null for a run without a lock, for a
 * LOCK record and for a record that is none of the fake's world.
 */
export function rerunRefusal(lockId: string | null, locks: readonly LockScope[]): Response | null {
  const record = locks.find((item) => item.id === lockId);
  const refused = record === undefined ? null : notALock(record);
  return refused === null
    ? null
    : invalid([{ field: AS_LOCKED.field, rule_id: AS_LOCKED.rule_id, message: refused }]);
}
