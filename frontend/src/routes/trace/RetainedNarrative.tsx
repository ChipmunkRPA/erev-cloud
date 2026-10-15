// A bookmarked narrative reauthorizes its source; the call log never carries its content.
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useAccess } from "../../lib/access";
import { fetchProposal, proposalKey } from "../../lib/api/queries/ai";
import { t } from "../../lib/i18n/t";

export function RetainedNarrative({
  traceId,
  proposalId,
}: {
  readonly traceId: string;
  readonly proposalId: string;
}) {
  const allowed = useAccess().holdsAnywhere("ai.use");
  const read = useQuery({
    queryKey: proposalKey(proposalId),
    queryFn: () => fetchProposal(proposalId),
    enabled: allowed,
    staleTime: 0,
    refetchOnMount: "always",
  });
  const proposal = read.data?.proposal;
  if (
    !allowed ||
    read.isError ||
    (proposal !== undefined &&
      (proposal.kind !== "NUMBER_EXPLANATION" || proposal.subject_id !== traceId))
  ) {
    return <Banner tone="info" title={t("ai.narrative.unavailable")} />;
  }
  if (read.isFetching || proposal === undefined)
    return <Skeleton region={t("ai.narrative.title")} shape="rows" count={2} />;
  if (proposal.kind !== "NUMBER_EXPLANATION") return null;
  const narrative = proposal.content.narrative;
  const lines =
    Array.isArray(narrative) && narrative.every((line) => typeof line === "string")
      ? narrative
      : [];
  return (
    <section
      aria-label={t("ai.narrative.title")}
      className="flex flex-col gap-2 rounded-lg border border-dashed border-hairline p-4"
    >
      <h2 className="text-title-sm">{t("ai.narrative.title")}</h2>
      <p>{t("ai.narrative.notice")}</p>
      <p>{t("ai.narrative.status", { status: proposal.status })}</p>
      {proposal.status === "failed" || lines.length === 0 ? (
        <p>{t("ai.narrative.failed")}</p>
      ) : (
        <>
          {lines.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
          <ul>
            {proposal.citations
              .filter(
                (citation) =>
                  citation.ref_type === "record" &&
                  citation.ref_id === traceId &&
                  typeof citation.node_id === "string",
              )
              .map((citation, index) => (
                <li key={index}>
                  <Link
                    to={`/trace/${encodeURIComponent(traceId)}?proposal=${encodeURIComponent(proposalId)}&node=${encodeURIComponent(String(citation.node_id))}`}
                  >
                    {t("ai.narrative.source", { node: String(citation.node_id) })}
                  </Link>
                </li>
              ))}
          </ul>
        </>
      )}
    </section>
  );
}
