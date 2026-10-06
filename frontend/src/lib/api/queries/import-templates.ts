// Import templates (04 API-R-43 `GET /import-templates`, `GET /import-templates/{code}/download`;
// API-S-ImportTemplate; T-IMP-01; 05 UPL-10; SCREENS §12.4; BUILD_SPEC DIN-15).
import messages from "../../../messages/en.json";
import { t } from "../../i18n/t";
import { send } from "../client";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type ImportTemplate = components["schemas"]["ImportTemplateOut"];
export type ImportTemplateFamily = ImportTemplate["family"];

export const IMPORT_TEMPLATES_PATH = "/api/v1/import-templates";
/** SCREENS §12.4 Family chip literals, legacy v1 first. */
export const TEMPLATE_FAMILIES: readonly ImportTemplateFamily[] = ["LEGACY_V1", "CSV_V2"];

const PARAMETER_KEYS: Readonly<Record<string, string>> = {
  effective_date: "data.templates.parameter.effectiveDate",
  mode: "data.templates.parameter.mode",
};

export function importTemplatesKey(): QueryKey {
  return queryKey("import-templates", "tenant", { view: "list" });
}

/** `GET /import-templates`: the current version of every template on one page. */
export async function fetchImportTemplates(): Promise<readonly ImportTemplate[]> {
  const response = await send("GET", IMPORT_TEMPLATES_PATH);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const body = (await response.json()) as { readonly items: readonly ImportTemplate[] };
  return body.items;
}

const CATALOGUE: Readonly<Record<string, string>> = messages;

/**
 * SCREENS §12.4 template names by code ("Legacy v1: SKU SSP", "Progress events (CSV v2)"); a code
 * without catalogue copy shows the API `name`. [J] L6-4-Q-12: the seeded `import_template.name` values
 * carry no family ("SKU SSP", "Progress events").
 */
export function templateName(template: Pick<ImportTemplate, "code" | "name">): string {
  const key = `data.templates.name.${template.code}`;
  return CATALOGUE[key] === undefined ? template.name : t(key);
}

/** The outline chip "Legacy v1" or "CSV v2". */
export function familyLabel(family: ImportTemplateFamily): string {
  return t(`data.templates.family.${family}`);
}

/** SCREENS §12.4 Parameters: the labels of `required_parameters`; an unknown name shows as is. */
export function parameterLabels(template: Pick<ImportTemplate, "required_parameters">): string[] {
  return template.required_parameters.map((parameter) => {
    const key = PARAMETER_KEYS[parameter.name];
    return key === undefined ? parameter.name : t(key);
  });
}

export function downloadFilename(template: Pick<ImportTemplate, "code">): string {
  return `${template.code}.xlsx`;
}

/**
 * `GET /import-templates/{code}/download` saved as `<code>.xlsx`: the headers, one example row and
 * the sheet "Definitions" (REQ-DAT-016). Throws the `ApiProblem` of a refused download.
 */
export async function downloadTemplate(
  template: Pick<ImportTemplate, "code" | "download_href">,
): Promise<void> {
  const response = await send("GET", template.download_href);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = downloadFilename(template);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
