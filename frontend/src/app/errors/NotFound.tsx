// Not found (X:not-found, RT-98; SCREENS §0.4, §0.7 SCR-ST-07; SCREENS_B §12.4). The route `*`, and a
// route whose path parameter does not match its SCREENS §0.4 pattern, render the page-level empty
// state "Page not found" with the action "Go to Home", which opens the landing route (BS-D-08).
import { Outlet, type Params, useMatches, useNavigate } from "react-router";

import { Button } from "../../components/ui/Button";
import { t } from "../../lib/i18n/t";

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const DASHBOARD_CODE_PATTERN = /^[a-z][a-z0-9_]*$/;

/** SCREENS §0.4: the path parameters that match a lowercase UUID. */
export const UUID_PARAMS: ReadonlySet<string> = new Set([
  "contractId",
  "obligationId",
  "estimateId",
  "modificationId",
  "importId",
  "exceptionId",
  "connectionId",
  "syncRunId",
  "requestId",
  "templateId",
  "ruleSetId",
  "versionId",
  "policyId",
  "bookId",
  "runId",
  "mappingVersionId",
  "customerId",
  "productId",
  "proposalId",
  "packId",
  "verificationId",
  "eventSetId",
  "migrationId",
  "calcTraceId",
  "reconciliationId",
  "membershipId",
  "reviewId",
]);

/** True when every UUID parameter is a lowercase UUID and `dashboardCode` matches its pattern. */
export function paramsMatch(params: Params): boolean {
  return Object.entries(params).every(([name, value]) => {
    if (value === undefined) {
      return true;
    }
    if (UUID_PARAMS.has(name)) {
      return UUID_PATTERN.test(value);
    }
    return name !== "dashboardCode" || DASHBOARD_CODE_PATTERN.test(value);
  });
}

export interface NotFoundProps {
  /** The landing route (BS-D-08), the target of "Go to Home". */
  readonly homePath: string;
}

export function NotFound({ homePath }: NotFoundProps) {
  const navigate = useNavigate();
  return (
    <div data-testid="X-page" className="flex max-w-120 flex-col items-start gap-2 pt-12">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {t("errors.notFound.title")}
      </h1>
      <p className="text-body-sm text-fg-2">{t("errors.notFound.description")}</p>
      <div className="mt-2">
        <Button variant="primary" onClick={() => void navigate(homePath)}>
          {t("errors.notFound.goHome")}
        </Button>
      </div>
    </div>
  );
}

/** The child route, or NotFound when a path parameter does not match its pattern (SCREENS §0.4). */
export function ParamGuard({ homePath }: NotFoundProps) {
  const matches = useMatches();
  const params = matches.at(-1)?.params ?? {};
  return paramsMatch(params) ? <Outlet /> : <NotFound homePath={homePath} />;
}
