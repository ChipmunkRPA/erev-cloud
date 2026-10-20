import { useState } from "react";
import { Link } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import type { ForecastInput } from "../../lib/api/queries/forecasts";
import { t } from "../../lib/i18n/t";

const label = (key: string) => t(`reports.inputs.review.${key}`);
const words = (key: string) => key.replaceAll("_", " ").toLowerCase();
type ReviewInput = Pick<ForecastInput, "api_commands" | "import_upload_ids" | "input_sequence">;
type Entry = { kind: "command"; index: number } | { kind: "import"; id: string };
function ordered(row: ReviewInput): Entry[] | null {
  if (!row.input_sequence)
    return row.api_commands.length + row.import_upload_ids.length === 0 ? [] : null;
  const result: Entry[] = [];
  let command = 0;
  let upload = 0;
  for (const entry of row.input_sequence) {
    if (
      Object.keys(entry).length === 2 &&
      entry.kind === "API_COMMAND" &&
      entry.index === command &&
      command < row.api_commands.length
    ) {
      result.push({ kind: "command", index: command++ });
    } else if (
      Object.keys(entry).length === 2 &&
      entry.kind === "IMPORT_UPLOAD" &&
      typeof entry.id === "string" &&
      entry.id === row.import_upload_ids[upload]
    ) {
      result.push({ kind: "import", id: entry.id });
      upload++;
    } else return null;
  }
  return command === row.api_commands.length &&
    upload === row.import_upload_ids.length &&
    new Set(row.import_upload_ids).size === upload
    ? result
    : null;
}
/** Preserve every captured value, including decimal strings, without coercion or HTML rendering. */
function Value({ value }: { readonly value: unknown }) {
  if (value === null || value === undefined) return <span>{label("unset")}</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ul className="flex flex-col gap-2">
        {value.map((item: unknown, index) => (
          <li key={index}>
            <Value value={item} />
          </li>
        ))}
      </ul>
    ) : (
      <span>{label("empty")}</span>
    );
  if (typeof value === "object") {
    return (
      <dl className="grid grid-cols-[minmax(8rem,1fr)_3fr] gap-2">
        {Object.entries(value).map(([key, item]) => (
          <div key={key} className="contents">
            <dt className="text-fg-2">{words(key)}</dt>
            <dd className="min-w-0 break-words">
              <Value value={item} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="whitespace-pre-wrap break-all">{String(value)}</span>;
}
export function ForecastInputReview({ row }: { readonly row: ReviewInput }) {
  const [open, setOpen] = useState(false);
  const access = useAccess();
  const entries = ordered(row);
  return (
    <section className="flex flex-col gap-2">
      <Button variant="secondary" onClick={() => setOpen(!open)}>
        {label(open ? "hide" : "show")}
      </Button>
      {open ? (
        <>
          <p>{label("basis")}</p>
          {entries === null ? (
            <Banner tone="negative" title={label("orderMissing")} />
          ) : entries.length === 0 ? (
            <p>{label("baseline")}</p>
          ) : (
            <ol className="flex list-decimal flex-col gap-3 pl-6">
              {entries.map((entry, index) => (
                <li key={index}>
                  {entry.kind === "import" ? (
                    <>
                      <p>
                        {label("import")}: {entry.id}
                      </p>
                      {access.holdsAnywhere("contract.read") ? (
                        <Link
                          className="underline"
                          to={`/data/imports/${encodeURIComponent(entry.id)}`}
                        >
                          {label("openImport")}
                        </Link>
                      ) : null}
                    </>
                  ) : (
                    (() => {
                      const command = row.api_commands[entry.index];
                      const path = typeof command?.path === "string" ? command.path : "";
                      const contract = /^\/contracts\/([0-9a-f-]{36})\/events$/i.exec(path)?.[1];
                      return (
                        <div className="flex flex-col gap-2">
                          <p>
                            {label("change")}
                            {contract ? ` · ${contract}` : ""}
                          </p>
                          {contract && access.holdsAnywhere("contract.read") ? (
                            <Link
                              className="underline"
                              to={`/contracts/${encodeURIComponent(contract)}`}
                            >
                              {label("openContract")}
                            </Link>
                          ) : null}
                          <Value value={command?.body} />
                        </div>
                      );
                    })()
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      ) : null}
    </section>
  );
}
