// Configuration example cases (04 API-R-57 `GET, POST /config-test-cases`, `PATCH, DELETE
// /config-test-cases/{id}`; T-REF-27; SCREENS §11.1 test cases panel; BUILD_SPEC RFD-22). A case names
// its subject (`rule_set_version`, `pob_template_version`, `account_mapping_version`,
// `registry_version`); it changes only while the subject version is DRAFT or TESTED (DB-04).
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type ConfigTestCase = components["schemas"]["ConfigTestCaseOut"];
export type ConfigTestCaseCreate = components["schemas"]["ConfigTestCaseIn"];
export type ConfigSubjectType = ConfigTestCaseCreate["subject_type"];

export const CONFIG_TEST_CASES_PATH = "/api/v1/config-test-cases";

export function configTestCasesKey(subjectType: ConfigSubjectType, subjectId: string): QueryKey {
  return queryKey("config-test-cases", "tenant", {
    subject_type: subjectType,
    subject_id: subjectId,
  });
}

export function configTestCasePath(caseId: string): string {
  return `${CONFIG_TEST_CASES_PATH}/${caseId}`;
}

/** One DataGrid page of the example cases of one configuration version (DG-FE-07). */
export function fetchConfigTestCasesPage(
  subjectType: ConfigSubjectType,
  subjectId: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ConfigTestCase>> {
  return fetchListPage<ConfigTestCase>(
    CONFIG_TEST_CASES_PATH,
    { subject_type: subjectType, subject_id: subjectId, sort },
    cursor,
  );
}

/** SCREENS §11.1 Last result chips: `PASS` "Succeeded", `FAIL` "Failed"; null before a run. */
export function caseResultWord(
  result: ConfigTestCase["last_result"],
): "Succeeded" | "Failed" | null {
  if (result === "PASS") {
    return "Succeeded";
  }
  return result === "FAIL" ? "Failed" : null;
}

export type JsonObjectParse =
  { readonly ok: true; readonly value: Readonly<Record<string, unknown>> } | { readonly ok: false };

/** SCREENS §11.1 "Add test case": the textarea must hold a JSON object. */
export function parseJsonObject(text: string): JsonObjectParse {
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      return { ok: true, value: value as Record<string, unknown> };
    }
  } catch {
    // Not JSON: refused below.
  }
  return { ok: false };
}

/** The mono one-line summary of a case's input or expected output, for example `{"rule_key":"R-1"}`. */
export function jsonSummary(value: Readonly<Record<string, unknown>>): string {
  return JSON.stringify(value);
}
