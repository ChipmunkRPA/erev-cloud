import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import type { EvidencePack } from "../../lib/api/queries/evidence-packs";
import { t } from "../../lib/i18n/t";

// Exact first-close payload names from evidence_assembly.REQUIRED_PATHS.
// Presence describes the retained manifest, not verification of archive bytes.
const sections = [
  { key: "certification", paths: ["certification.json"] },
  {
    key: "lock",
    paths: ["lock/snapshots.json", "lock/approvals.json", "lock/source_binding.json"],
  },
  { key: "journals", paths: ["journals/batch_register.json", "journals/je_population.csv"] },
  {
    key: "reconciliations",
    paths: ["reconciliations/index.json", "reconciliations/population.json"],
  },
  {
    key: "rollforwards",
    paths: [
      "reports/contract_balance_rollforward.csv",
      "reports/rpo_rollforward.csv",
      "reports/contract_cost_rollforward.csv",
    ],
  },
  { key: "rpo", paths: ["reports/rpo.csv", "reports/disaggregation.csv"] },
  {
    key: "registers",
    paths: [
      "registers/manual_adjustment_register.csv",
      "registers/modification_register.csv",
      ...supporting("registers/ssp_change_log"),
      ...supporting("registers/config_change_register"),
    ],
  },
  { key: "late", paths: [...supporting("registers/late_entries"), "registers/out_of_period.csv"] },
  {
    key: "access",
    paths: [
      ...supporting("access/user_access_listing"),
      ...supporting("access/sod_conflict_report"),
    ],
  },
  { key: "audit", paths: ["audit/chain_digest.json", "audit/sources.json"] },
  {
    key: "population",
    paths: [
      "reports/revenue_waterfall.csv",
      "reports/contract_balances.csv",
      "reports/revenue_from_prior_period_obligations.csv",
    ],
  },
] as const;
function supporting(prefix: string): string[] {
  return ["csv", "manifest.json", "source.json"].map((suffix) => `${prefix}.${suffix}`);
}

export function ClosePackContents({
  pack,
}: {
  readonly pack: Extract<EvidencePack, { kind: "CLOSE" }>;
}) {
  if (pack.status !== "SUCCEEDED" || pack.manifest === null) return null;
  const paths = new Set(pack.manifest.files.map((file) => file.path));
  const rows: { key: string; missing: string[] }[] = sections.map((section) => ({
    key: section.key,
    missing: section.paths.filter((path) => !paths.has(path)),
  }));
  // The manifest is outside its own payload list to avoid a self-referential hash.
  rows.push({ key: "manifest", missing: pack.manifest_sha256 === null ? ["manifest.json"] : [] });
  return (
    <section className="space-y-4">
      <h2 className="text-title-md">{t("evidence.contents.title")}</h2>
      <p>{t("evidence.contents.description")}</p>
      <table className="w-full text-start text-body-sm" data-testid="SF-09-grid-pack-contents">
        <caption className="sr-only">{t("evidence.contents.title")}</caption>
        <thead>
          <tr>
            <th scope="col" className="p-2">
              {t("evidence.contents.section")}
            </th>
            <th scope="col" className="p-2">
              {t("evidence.contents.status")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-hairline">
              <th scope="row" className="p-2 font-normal">
                {t(`evidence.contents.${row.key}`)}
              </th>
              <td className="p-2">
                {row.missing.length === 0 ? (
                  <OutlineChip label={t("evidence.contents.present")} />
                ) : (
                  <StatusChip status="Difference" caption={t("evidence.contents.missing")} />
                )}
                {row.missing.length === 0 ? null : (
                  <ul
                    aria-label={t("evidence.contents.missingFiles")}
                    className="break-all font-mono text-mono-sm"
                  >
                    {row.missing.map((path) => (
                      <li key={path}>{path}</li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
