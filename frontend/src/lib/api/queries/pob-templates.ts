// Obligation templates and their versions (04 API-R-24 `GET /pob-templates`, `GET /pob-templates/{id}`,
// `GET, POST /pob-templates/{id}/versions`, `GET, PATCH /pob-template-versions/{id}` with `If-Match`,
// `POST /pob-template-versions/{id}/test`, `/submit`; API-R-57 config test cases of subject
// `pob_template_version`; T-REF-22, T-REF-23; E-11, E-18; REQ-POL-001; SCREENS §11.2; BUILD_SPEC RFD-23).
// A template version carries the outputs an obligation receives (kind, distinctness, satisfaction
// pattern, measure of progress, date rules, principal or agent, warranty, licence nature, revenue
// category, account overrides) and product-level policy values. Publication runs through the approval
// (D-76), so no publish command is exposed here. Commands go through `useCommand` from the screen.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { POB_TEMPLATES_PATH, type PobTemplate, type PobTemplateVersion } from "./rule-sets";
import { STRUCTURE_LIMIT } from "./tenant";

export type { PobTemplate, PobTemplateVersion };
export type PobTemplateVersionUpdate = components["schemas"]["PobTemplateVersionUpdateIn"];
export type PobTemplateVersionCreate = components["schemas"]["PobTemplateVersionIn"];
export type PobTemplateVersionSubmit = components["schemas"]["PobTemplateVersionSubmitIn"];
export type ObligationKind = components["schemas"]["ObligationKind"];
export type SatisfactionPattern = components["schemas"]["SatisfactionPattern"];
export type OverTimeCriterion = components["schemas"]["OverTimeCriterion"];
export type RecognitionMethod = components["schemas"]["RecognitionMethod"];
export type RatableConvention = components["schemas"]["RatableConvention"];
export type WarrantyType = components["schemas"]["WarrantyType"];
export type LicenceNature = components["schemas"]["LicenceNature"];
export type Distinctness = components["schemas"]["Distinctness"];
export type PrincipalAgent = components["schemas"]["PrincipalAgent"];
export type StartDateRule = PobTemplateVersion["start_date_rule"];
export type EndDateRule = PobTemplateVersion["end_date_rule"];
export type SeriesIncrementUnit = NonNullable<PobTemplateVersion["series_increment_unit"]>;

export const POB_TEMPLATE_VERSIONS_PATH = "/api/v1/pob-template-versions";
/** SCREENS RT-61 SF-13:template-version, `pane=outputs|policy-values|tests|simulation|changes`. */
export const TEMPLATE_VERSION_ROUTE = "/policies/templates/:templateId/versions/:versionId";

export type TemplatePane = "outputs" | "policy-values" | "tests" | "simulation" | "changes";
export const TEMPLATE_PANES: readonly TemplatePane[] = [
  "outputs",
  "policy-values",
  "tests",
  "simulation",
  "changes",
];

export function templatePaneOf(value: string | null): TemplatePane {
  return TEMPLATE_PANES.find((pane) => pane === value) ?? "outputs";
}

/** E-18 literals in 04 order. */
export const OBLIGATION_KINDS: readonly ObligationKind[] = [
  "STANDARD",
  "VC_LINE",
  "MATERIAL_RIGHT",
  "SERVICE_WARRANTY",
  "CUSTODIAL",
  "LICENCE",
  "SHIPPING",
];
export const DISTINCTNESS_VALUES: readonly Distinctness[] = ["distinct", "nondistinct", "series"];
export const SERIES_UNITS: readonly SeriesIncrementUnit[] = ["day", "month", "transaction", "unit"];
export const SATISFACTION_PATTERNS: readonly SatisfactionPattern[] = ["POINT_IN_TIME", "OVER_TIME"];
export const OVER_TIME_CRITERIA: readonly OverTimeCriterion[] = ["OT_A", "OT_B", "OT_C"];
/** E-11 literals in 04 order. */
export const RECOGNITION_METHODS: readonly RecognitionMethod[] = [
  "POINT_IN_TIME",
  "TIME_ELAPSED",
  "UNITS_DELIVERED",
  "OUTPUT_PERCENT",
  "MILESTONE",
  "COST_TO_COST",
  "LABOUR_HOURS",
  "RIGHT_TO_INVOICE",
  "COST_RECOVERY",
];
/** SCREENS §11.2: a point-in-time template offers only these methods. */
export const POINT_IN_TIME_METHODS: readonly RecognitionMethod[] = [
  "POINT_IN_TIME",
  "UNITS_DELIVERED",
];
export const RATABLE_CONVENTIONS: readonly RatableConvention[] = [
  "DAILY",
  "MONTHLY_EVEN",
  "MID_MONTH",
];
export const START_DATE_RULES: readonly StartDateRule[] = [
  "LINE_START",
  "BOOKING_DATE",
  "CONTROL_TRANSFER",
  "FIRST_USAGE",
  "LICENCE_START_OR_AVAILABLE",
];
export const END_DATE_RULES: readonly EndDateRule[] = ["LINE_END", "START_PLUS_TERM", "NONE"];
export const PRINCIPAL_AGENT_VALUES: readonly PrincipalAgent[] = [
  "PRINCIPAL",
  "AGENT",
  "NOT_ASSESSED",
];
export const WARRANTY_TYPES: readonly WarrantyType[] = ["ASSURANCE", "SERVICE", "NONE"];
export const LICENCE_NATURES: readonly LicenceNature[] = [
  "FUNCTIONAL",
  "SYMBOLIC",
  "NOT_APPLICABLE",
];

/** Every template version read, for invalidation after a command. */
export const EVERY_TEMPLATE: QueryKey = queryKey("pob-templates", "tenant");
export const EVERY_TEMPLATE_VERSION: QueryKey = queryKey("pob-template-versions", "tenant");

export function templateKey(templateId: string): QueryKey {
  return queryKey("pob-templates", "tenant", { id: templateId });
}

export function fetchTemplate(templateId: string): Promise<PobTemplate> {
  return unwrap(
    api.GET("/api/v1/pob-templates/{template_id}", {
      params: { path: { template_id: templateId } },
    }),
  );
}

export function useTemplate(templateId: string) {
  return useQuery({ queryKey: templateKey(templateId), queryFn: () => fetchTemplate(templateId) });
}

export function templateVersionsKey(templateId: string): QueryKey {
  return queryKey("pob-template-versions", "tenant", { template: templateId });
}

export function templateVersionsPath(templateId: string): string {
  return `${POB_TEMPLATES_PATH}/${templateId}/versions`;
}

/** The versions of a template, newest first. */
export async function fetchTemplateVersions(
  templateId: string,
): Promise<readonly PobTemplateVersion[]> {
  const page = await fetchListPage<PobTemplateVersion>(
    templateVersionsPath(templateId),
    { sort: "-version_no" },
    null,
    { limit: STRUCTURE_LIMIT, count: false },
  );
  return page.items;
}

export function templateVersionKey(versionId: string): QueryKey {
  return queryKey("pob-template-versions", "tenant", { id: versionId });
}

export function templateVersionPath(versionId: string): string {
  return `${POB_TEMPLATE_VERSIONS_PATH}/${versionId}`;
}

export function fetchTemplateVersion(versionId: string): Promise<PobTemplateVersion> {
  return unwrap(
    api.GET("/api/v1/pob-template-versions/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

export function useTemplateVersion(versionId: string) {
  return useQuery({
    queryKey: templateVersionKey(versionId),
    queryFn: () => fetchTemplateVersion(versionId),
  });
}

export function templateVersionRoute(templateId: string, versionId: string): string {
  return `/policies/templates/${templateId}/versions/${versionId}`;
}

/** SCREENS §11.0: outputs change only while the version is DRAFT or TESTED (DB-04). */
export function isTemplateEditable(version: Pick<PobTemplateVersion, "status">): boolean {
  return version.status === "DRAFT" || version.status === "TESTED";
}

/** The output fields of a version compared in the Changes pane (T-REF-23 columns, SCREENS §11.2). */
export const OUTPUT_FIELDS = [
  "obligation_kind",
  "distinctness",
  "series_increment_unit",
  "satisfaction_pattern",
  "over_time_criterion",
  "recognition_method",
  "ratable_convention",
  "start_date_rule",
  "end_date_rule",
  "term_months",
  "principal_agent",
  "warranty_type",
  "licence_nature",
  "sfc_assessment_required",
  "revenue_category",
  "stratification_label",
  "is_excluded_from_netting_attribution",
] as const;
export type OutputField = (typeof OUTPUT_FIELDS)[number];

export interface OutputChange {
  readonly field: OutputField;
  readonly before: unknown;
  readonly after: unknown;
}

/** The output fields whose values differ between a version and the one it supersedes. */
export function outputChanges(
  version: PobTemplateVersion,
  previous: PobTemplateVersion | null,
): readonly OutputChange[] {
  if (previous === null) {
    return [];
  }
  return OUTPUT_FIELDS.filter((field) => version[field] !== previous[field]).map((field) => ({
    field,
    before: previous[field],
    after: version[field],
  }));
}

/** The registry parameters a template may carry as product-level values (SCREENS §11.2). */
export function productLevelParameters<T extends { readonly allowed_levels: readonly string[] }>(
  parameters: readonly T[],
): readonly T[] {
  return parameters.filter((parameter) => parameter.allowed_levels.includes("PRODUCT"));
}
