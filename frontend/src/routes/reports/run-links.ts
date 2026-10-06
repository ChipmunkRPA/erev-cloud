// The report view of a run (SCREENS_B §5.3 "Open report view"; §0.5 RV-01; SCREENS SCR-URL-01 to
// SCR-URL-06, SCR-URL-16 `run`; BUILD_SPEC RPS-18). A run opens in SF-08:report with its own parameters
// as the view's URL carries them — the inverse of `runParameters` (viewer/specs): `entity_codes` of one
// entity is `entity` and of several is `entities=all` (SCREENS SCR-URL-01 rev 1.61), `book` is `book`,
// `period_key` is `period`, `period_lock_id` is `snapshot`, a supplied `known_at` and `currency_view`
// keep their names and every other key is `p.<key>`. A JSON run adds `run=<id>`, so the view renders the
// stored run and creates none; a file run opens the view on the same parameters, which creates a run to
// show. The two pack reports have no report view.
import type { ReportRun } from "../../lib/api/queries/reports";
import { withParams } from "../../lib/url/params";
import { PACK_CODES } from "./viewer/specs";
import { ALL_ENTITIES, ENTITIES_PARAM } from "./viewer/useViewContext";

const PARAMETER_PREFIX = "p.";
const RUN_PARAM = "run";
/** Run parameters the view reads from its context: parameter key → URL parameter. */
const CONTEXT: Readonly<Record<string, string>> = {
  book: "book",
  period_key: "period",
  period_lock_id: "snapshot",
  currency_view: "currency_view",
};

/** A parameter value as the view's URL carries it; null for a value no URL parameter holds. */
function carried(value: unknown): string | null {
  if (typeof value === "string") {
    return value === "" ? null : value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => typeof item === "string" || typeof item === "number")
  ) {
    return value.join(",");
  }
  return null;
}

/** True for a run whose rows the view renders from the stored run: a JSON run, or one without output. */
export function isViewRun(run: Pick<ReportRun, "output">): boolean {
  return run.output === null || run.output.format === "JSON";
}

/** The search of SF-08:report for the run's parameters, with `run` for a JSON run. */
export function reportViewSearch(run: Pick<ReportRun, "id" | "parameters" | "output">): string {
  const changes: Record<string, string | null> = {};
  for (const [key, value] of Object.entries(run.parameters)) {
    if (key === "entity_codes") {
      // The view's context names one entity. A run of several says "all entities" (SCR-URL-01 rev
      // 1.61): an address that names no entity is no longer every entity in scope but the pill's, and
      // the view would stand in one entity around a run of several.
      if (Array.isArray(value) && value.length === 1 && typeof value[0] === "string") {
        changes.entity = encodeURIComponent(value[0]);
      } else if (Array.isArray(value) && value.length > 1) {
        changes[ENTITIES_PARAM] = ALL_ENTITIES;
      }
    } else if (key === "known_at") {
      // Only a cutoff the caller supplied is a parameter of the view (`known_at_basis` historical).
      if (run.parameters.known_at_basis === "historical" && typeof value === "string") {
        changes.known_at = encodeURIComponent(value);
      }
    } else if (key !== "known_at_basis") {
      const text = carried(value);
      if (text !== null) {
        changes[CONTEXT[key] ?? `${PARAMETER_PREFIX}${key}`] = encodeURIComponent(text);
      }
    }
  }
  if (isViewRun(run)) {
    changes[RUN_PARAM] = run.id;
  }
  return withParams("", changes);
}

/** SF-08:report for the run, or null for a report without a report view. */
export function reportViewHref(
  run: Pick<ReportRun, "id" | "report" | "parameters" | "output">,
): string | null {
  return PACK_CODES.has(run.report.code)
    ? null
    : `/reports/${run.report.code}${reportViewSearch(run)}`;
}
