import { t } from "../../lib/i18n/t";
import type { components } from "../../lib/api/schema";
type Preview = components["schemas"]["PortfolioBreakagePreviewOut"];
const label = (key: string) => t(`settings.portfolioAllocation.${key}`);

export function AllocationTable({ value }: { readonly value: Preview }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-body-sm">
        <caption>{label("sources")}</caption>
        <thead>
          <tr>
            {["contract", "obligation", "ssp", "entitlement", "quantity", "version"].map((key) => (
              <th key={key} scope="col" className="p-2">
                {label(key)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {value.shares.map((share) => (
            <tr key={`${share.contract_id}:${share.obligation_id}`}>
              <td className="p-2">{share.contract_external_id}</td>
              <td className="p-2">{share.obligation_key}</td>
              <td className="p-2">
                {share.ssp} {value.currency}
                {share.ssp_conversion ? (
                  <details>
                    <summary>{label("conversion")}</summary>
                    <p>
                      {share.ssp_conversion.original_ssp} {share.ssp_conversion.source_currency}
                      {" × "}
                      {share.ssp_conversion.rate}
                      {" = "}
                      {share.ssp} {share.ssp_conversion.target_currency}
                    </p>
                    <p>
                      {label("effectiveDate")}: {share.ssp_conversion.effective_date}
                    </p>
                    <p>
                      {label("rateSource")}: {share.ssp_conversion.rate_key}
                      {" · "}
                      {share.ssp_conversion.rate_version_key}
                      {" · "}
                      {share.ssp_conversion.rate_date}
                    </p>
                  </details>
                ) : null}
              </td>
              <td className="p-2">{share.entitlement_quantity}</td>
              <td className="p-2">{share.breakage_quantity}</td>
              <td className="p-2">
                <details>
                  <summary>{share.contract_version_id}</summary>
                  <p>{share.computation_id}</p>
                  <p className="break-all">{share.computation_output_sha256}</p>
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
