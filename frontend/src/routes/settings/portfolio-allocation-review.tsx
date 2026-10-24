import { t } from "../../lib/i18n/t";
import type { components } from "../../lib/api/schema";
import { AllocationTable } from "./portfolio-allocation-table";

type Preview = components["schemas"]["PortfolioBreakagePreviewOut"];
type Share = Preview["shares"][number];
const label = (key: string) => t(`settings.portfolioAllocation.${key}`);

function savedPreview(snapshot: unknown): Preview | null {
  if (
    !snapshot ||
    typeof snapshot !== "object" ||
    !("schema_version" in snapshot) ||
    snapshot.schema_version !== 1 ||
    !("allocation" in snapshot)
  )
    return null;
  const value = snapshot.allocation;
  if (!value || typeof value !== "object" || !("shares" in value) || !Array.isArray(value.shares))
    return null;
  // Saved snapshots are server-validated. Refuse unfamiliar/incomplete display shapes.
  for (const key of [
    "book_code",
    "currency",
    "effective_date",
    "allocated_total",
    "total_breakage_quantity",
  ]) {
    if (!(key in value) || typeof (value as Record<string, unknown>)[key] !== "string") return null;
  }
  if (
    value.shares.some(
      (share: unknown) =>
        !share ||
        typeof share !== "object" ||
        [
          "contract_id",
          "contract_external_id",
          "obligation_id",
          "obligation_key",
          "ssp",
          "entitlement_quantity",
          "breakage_quantity",
          "contract_version_id",
          "computation_id",
          "computation_output_sha256",
        ].some((key) => typeof (share as Record<string, unknown>)[key] !== "string"),
    )
  )
    return null;
  return value as Preview;
}

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`)
      .join(",")}}`;
  return JSON.stringify(value) ?? "null";
}
const target = (share: Share) => `${share.contract_id}:${share.obligation_id}`;
const comparable = (value: Preview) => ({
  ...value,
  shares: [...value.shares].sort((a, b) => target(a).localeCompare(target(b))),
});

export function SavedAllocation({
  code,
  snapshot,
}: {
  readonly code: string;
  readonly snapshot: unknown;
}) {
  const saved = savedPreview(snapshot);
  return (
    <details>
      <summary>
        {label("retained")}: {code}
      </summary>
      {saved ? (
        <>
          <p>
            {label("effectiveDate")}: {saved.effective_date} · {saved.currency} · {label("total")}:{" "}
            {saved.allocated_total} / {saved.total_breakage_quantity}
          </p>
          <AllocationTable value={saved} />
        </>
      ) : (
        <p>{label("savedUnavailable")}</p>
      )}
    </details>
  );
}

export function AllocationReview({
  current,
  saved,
}: {
  readonly current: Preview;
  readonly saved: unknown;
}) {
  const prior = savedPreview(saved);
  if (!prior) return <p>{label(saved ? "savedUnavailable" : "notSaved")}</p>;
  if (stable(comparable(prior)) === stable(comparable(current)))
    return <p role="status">{label("matchesPreview")}</p>;
  const previous = new Map(prior.shares.map((share) => [target(share), share]));
  const next = new Map(current.shares.map((share) => [target(share), share]));
  const changes = [...new Set([...previous.keys(), ...next.keys()])]
    .sort()
    .filter((key) => stable(previous.get(key)) !== stable(next.get(key)));
  return (
    <section aria-label={label("changes")}>
      <p role="status">{label("changedPreview")}</p>
      <p>
        {label("saved")}: {prior.effective_date} · {prior.book_code} · {prior.currency} ·{" "}
        {prior.total_breakage_quantity}
      </p>
      <p>
        {label("current")}: {current.effective_date} · {current.book_code} · {current.currency} ·{" "}
        {current.total_breakage_quantity}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-body-sm">
          <caption>{label("changes")}</caption>
          <thead>
            <tr>
              {["contract", "obligation", "change", "saved", "current"].map((key) => (
                <th key={key} scope="col" className="p-2">
                  {label(key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {changes.map((key) => {
              const old = previous.get(key),
                fresh = next.get(key),
                item = fresh ?? old;
              if (!item) return null;
              return (
                <tr key={key}>
                  <td className="p-2">{item.contract_external_id}</td>
                  <td className="p-2">{item.obligation_key}</td>
                  <td className="p-2">{label(!old ? "added" : !fresh ? "removed" : "changed")}</td>
                  {[old, fresh].map((share, index) => (
                    <td key={index} className="p-2">
                      {share ? (
                        <>
                          <p>
                            {label("quantity")}: {share.breakage_quantity}
                          </p>
                          <p>
                            {label("ssp")}: {share.ssp}{" "}
                            {index === 0 ? prior.currency : current.currency}
                          </p>
                          <p>
                            {label("entitlement")}: {share.entitlement_quantity}
                          </p>
                          <p>
                            {label("version")}: {share.contract_version_id}
                          </p>
                          {share.ssp_conversion ? (
                            <p>
                              {label("rateSource")}: {share.ssp_conversion.rate_key} ·{" "}
                              {share.ssp_conversion.rate_version_key} · {share.ssp_conversion.rate}
                            </p>
                          ) : null}
                          <details>
                            <summary>{label("computationSource")}</summary>
                            <p>{share.computation_id}</p>
                            <p className="break-all">{share.computation_output_sha256}</p>
                          </details>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
