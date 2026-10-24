import { useState } from "react";

import { useQuery } from "@tanstack/react-query";

import { Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { useCommand } from "../../lib/api/commands";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { ApiProblem } from "../../lib/api/problems";
import { readJson } from "../../lib/api/queries/contracts";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";

type Version = components["schemas"]["EstimateVersionOut"];
type Preview = components["schemas"]["PortfolioBreakagePreviewOut"];
import { AllocationTable } from "./portfolio-allocation-table";
import { AllocationReview, SavedAllocation } from "./portfolio-allocation-review";

const label = (key: string) => t(`settings.portfolioAllocation.${key}`);

export function PortfolioAllocation({
  path,
  revision,
  version,
  editable,
  onRetained,
}: {
  readonly path: string;
  readonly revision: string;
  readonly version: Version;
  readonly editable: boolean;
  readonly onRetained: (version: Version) => void;
}) {
  const [book, setBook] = useState("");
  const [networkError, setNetworkError] = useState(false);
  const retain = useCommand<Version>({
    method: "POST",
    path: path.replace(/allocation-preview$/, "retain-allocation"),
    ifMatch: rowIfMatch(version.row_version),
    invalidates: [queryKey("portfolios", "tenant")],
  });
  const previewPath = book ? `${path}?${new URLSearchParams({ book_code: book })}` : path;
  const preview = useQuery({
    queryKey: queryKey("portfolios", "tenant", { path, revision, book, view: "allocation" }),
    queryFn: async () => (await readJson<Preview>(previewPath)).data,
    // A different book must never display the previous book's allocation.
    placeholderData: () => undefined,
    enabled: false,
    retry: false,
  });
  return (
    <section className="flex flex-col gap-3" aria-label={label("title")}>
      <h4 className="text-heading-sm">{label("title")}</h4>
      <RefusalBanner problem={retain.problem} conflict={retain.banner} />
      {networkError ? <Banner tone="negative" title={label("networkError")} /> : null}
      {Object.entries(version.portfolio_application_basis?.breakage_allocations ?? {}).map(
        ([code, snapshot]) => (
          <SavedAllocation key={code} code={code} snapshot={snapshot} />
        ),
      )}
      <p className="text-body-sm text-fg-2">{label("help")}</p>
      <Field name="portfolio-allocation-book" label={label("book")}>
        {(control) => (
          <Select
            control={control}
            value={book}
            onChange={setBook}
            options={[
              { value: "", label: label("primaryBook") },
              ...(["ASC606", "IFRS15"] as const).map((value) => ({
                value,
                label: value,
              })),
            ]}
          />
        )}
      </Field>
      <Button loading={preview.isFetching} onClick={() => void preview.refetch()}>
        {label(preview.isFetching ? "loading" : "preview")}
      </Button>
      {preview.error instanceof ApiProblem ? (
        <RefusalBanner problem={preview.error} />
      ) : preview.isError ? (
        <Banner tone="negative" title={label("networkError")} />
      ) : null}
      {preview.data && !preview.isError && !preview.isFetching ? (
        <>
          <p>
            {label("total")}: {preview.data.allocated_total} /{" "}
            {preview.data.total_breakage_quantity}
            {" · "}
            {preview.data.book_code}
            {" · "}
            {preview.data.currency}
            {" · "}
            {label("effectiveDate")}: {preview.data.effective_date}
          </p>
          <AllocationReview
            current={preview.data}
            saved={
              version.portfolio_application_basis?.breakage_allocations?.[preview.data.book_code]
            }
          />
          {editable ? (
            <Button
              loading={retain.pending}
              onClick={() => {
                setNetworkError(false);
                void retain.submit(preview.data).then((outcome) => {
                  if (outcome.kind === "succeeded" && outcome.data) onRetained(outcome.data);
                  if (outcome.kind === "network-error") setNetworkError(true);
                });
              }}
            >
              {label("retain")}
            </Button>
          ) : null}
          <AllocationTable value={preview.data} />
        </>
      ) : null}
    </section>
  );
}
