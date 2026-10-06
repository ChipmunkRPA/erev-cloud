// SSP books and their versions (04 API-R-26 `GET, POST /ssp-books`, `GET, PATCH /ssp-books/{id}`,
// `GET, POST /ssp-books/{id}/versions`, `GET, PATCH /ssp-book-versions/{id}`, `GET, POST
// /ssp-book-versions/{id}/entries`, `DELETE …/entries/{entry_id}`, `GET …/diff`, `POST …/submit`,
// `/withdraw`; API-R-12 `POST /files` purpose `SSP_STUDY`, `GET, POST /attachments`; T-REF-28 to
// T-REF-31; SCREENS §11.4; BUILD_SPEC RFD-24). Decimals stay API-C-06 strings (DG-FE-08).
import { formatList, NO_VALUE } from "../../format";
import { t } from "../../i18n/t";
import { api, unwrap } from "../client";
import type { CommandKeys } from "../commands";
import { fetchListPage, type ListPage } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type SspBook = components["schemas"]["SspBookOut"];
export type SspBookVersion = components["schemas"]["SspBookVersionOut"];
export type SspEntry = components["schemas"]["SspEntryOut"];
export type SspEntryInput = components["schemas"]["SspEntryIn"];
export type SspRange = components["schemas"]["SspRangeOut"];
export type SspVersionDiff = components["schemas"]["SspVersionDiffOut"];
export type SspMethod = components["schemas"]["SspMethod"];
export type SspValueBasis = components["schemas"]["SspValueBasis"];
export type Distinctness = components["schemas"]["Distinctness"];
export type Attachment = components["schemas"]["AttachmentOut"];
export type StoredFile = components["schemas"]["FileOut"];
export type ResolutionMode = SspBook["resolution_mode"];
export type BandDimension = SspRange["band_dimension"];

export const SSP_BOOKS_PATH = "/api/v1/ssp-books";
export const SSP_BOOK_VERSIONS_PATH = "/api/v1/ssp-book-versions";
export const FILES_PATH = "/api/v1/files";
export const ATTACHMENTS_PATH = "/api/v1/attachments";
/** API-R-26: reads need `ssp.read`; books, versions, entries, study, submit and withdraw `ssp.create`. */
export const SSP_READ_PERMISSION = "ssp.read";
export const SSP_CREATE_PERMISSION = "ssp.create";
/** T-PLT-30 subject type of a version's study attachments. */
export const STUDY_SUBJECT_TYPE = "ssp_book_version";
/** 04 §15.2 ERR-10: a version submitted without a live `SSP_STUDY` attachment. */
export const STUDY_REQUIRED_SLUG = "ssp-study-required";
/** 04 §15.2 ERR-32: an approved version overlapping another. */
export const OVERLAP_SLUG = "configuration-overlap";

/** SCREENS §11.4 entries grid: the E-47 methods offered in the editor (`formula` is not offered). */
export const SSP_METHODS: readonly SspMethod[] = [
  "observable",
  "adjusted_market",
  "cost_plus_margin",
  "residual",
  "legacy_range",
];
/** E-49 bases offered in the editor; `PER_INCREMENT` and `PER_BOOKED_TERM` declare what a series
 *  product's entry prices (D-93 (4)). */
export const VALUE_BASES: readonly SspValueBasis[] = [
  "AMOUNT",
  "PERCENT_OF_LIST",
  "PER_INCREMENT",
  "PER_BOOKED_TERM",
];
export const DISTINCTNESS: readonly Distinctness[] = ["distinct", "nondistinct", "series"];
export const RESOLUTION_MODES: readonly ResolutionMode[] = ["EFFECTIVE_DATE", "BY_LABEL"];
export const BAND_DIMENSIONS: readonly BandDimension[] = [
  "NONE",
  "QUANTITY",
  "DEAL_SIZE",
  "TERM_MONTHS",
];

export function sspBooksKey(): QueryKey {
  return queryKey("ssp-books", "tenant", { view: "list" });
}

/** Every SSP book read, for invalidation after a command. */
export const EVERY_SSP_BOOK: QueryKey = queryKey("ssp-books", "tenant");
/** Every version read (versions, entries, diffs), for invalidation after a command. */
export const EVERY_SSP_BOOK_VERSION: QueryKey = queryKey("ssp-book-versions", "tenant");

export function sspBookKey(bookId: string): QueryKey {
  return queryKey("ssp-books", "tenant", { id: bookId });
}

export function sspBookVersionsKey(bookId: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { book: bookId });
}

export function sspBookVersionKey(versionId: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { id: versionId });
}

export function sspEntriesKey(versionId: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { id: versionId, view: "entries" });
}

export function sspDiffKey(versionId: string, against: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { id: versionId, view: "diff", against });
}

export function studyAttachmentsKey(versionId: string): QueryKey {
  return queryKey("attachments", "tenant", {
    subject_type: STUDY_SUBJECT_TYPE,
    subject_id: versionId,
  });
}

/** RT-66 SF-13:ssp-book-version. */
export function sspBookVersionRoute(bookId: string, versionId: string): string {
  return `/policies/ssp-books/${bookId}/versions/${versionId}`;
}

/** RT-66 note: `/policies/ssp-books/:bookId` redirects to the version `landingVersionId` names. */
export function sspBookRoute(bookId: string): string {
  return `/policies/ssp-books/${bookId}`;
}

export function sspBookVersionPath(versionId: string): string {
  return `${SSP_BOOK_VERSIONS_PATH}/${versionId}`;
}

/** One DataGrid page of `GET /ssp-books` (DG-FE-07). */
export function fetchSspBooksPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SspBook>> {
  return fetchListPage<SspBook>(SSP_BOOKS_PATH, { sort }, cursor);
}

async function fetchAll<T>(path: string, query: Readonly<Record<string, string>>): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<T> = await fetchListPage<T>(path, query, cursor, { count: false });
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

/** Every book in code order (the calculator's book select). */
export function fetchAllSspBooks(): Promise<readonly SspBook[]> {
  return fetchAll<SspBook>(SSP_BOOKS_PATH, { sort: "code" });
}

export function fetchSspBook(bookId: string): Promise<SspBook> {
  return unwrap(api.GET("/api/v1/ssp-books/{book_id}", { params: { path: { book_id: bookId } } }));
}

/** Every version of a book, newest first. */
export function fetchSspBookVersions(bookId: string): Promise<readonly SspBookVersion[]> {
  return fetchAll<SspBookVersion>(`${SSP_BOOKS_PATH}/${bookId}/versions`, {
    sort: "-version_no",
  });
}

export function fetchSspBookVersion(versionId: string): Promise<SspBookVersion> {
  return unwrap(
    api.GET("/api/v1/ssp-book-versions/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

/** One DataGrid page of the entries of a version in product order. */
export function fetchSspEntriesPage(
  versionId: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SspEntry>> {
  return fetchListPage<SspEntry>(`${sspBookVersionPath(versionId)}/entries`, { sort }, cursor);
}

/** Every entry of a version (the diff panel's unchanged entries). */
export function fetchAllSspEntries(versionId: string): Promise<readonly SspEntry[]> {
  return fetchAll<SspEntry>(`${sspBookVersionPath(versionId)}/entries`, { sort: "product_code" });
}

export function fetchSspDiff(versionId: string, against: string): Promise<SspVersionDiff> {
  return unwrap(
    api.GET("/api/v1/ssp-book-versions/{version_id}/diff", {
      params: { path: { version_id: versionId }, query: { against } },
    }),
  );
}

/** The live study attachments of a version, newest first. */
export async function fetchStudyAttachments(versionId: string): Promise<readonly Attachment[]> {
  const items = await fetchAll<Attachment>(ATTACHMENTS_PATH, {
    subject_type: STUDY_SUBJECT_TYPE,
    subject_id: versionId,
  });
  return items.filter((item) => item.voided_at === null);
}

/**
 * `POST /files` (multipart, API-R-12); identical content of the same purpose answers with the stored
 * file. Its Idempotency-Key is the key `keys` holds for the purpose and the file as the browser names
 * it (DG-FE-05 rev 1.156), so the same file sent again after a lost response carries the same key.
 * Throws the `ApiProblem` of a refusal; a network failure rejects.
 */
export async function uploadFile(
  keys: CommandKeys,
  purpose: string,
  file: File,
): Promise<StoredFile> {
  const form = new FormData();
  form.append("purpose", purpose);
  form.append("file", file, file.name);
  const response = await keys.send("POST", FILES_PATH, {
    form,
    step: [purpose, file.name, String(file.size), String(file.lastModified)].join(" "),
  });
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as StoredFile;
}

/** The version `/policies/ssp-books/:bookId` opens: the current approved version, else the draft,
 * else the newest version (L4-5-Q-51). */
export function landingVersionId(
  book: SspBook,
  versions: readonly SspBookVersion[],
): string | null {
  return book.current_version?.id ?? book.draft_version_id ?? versions[0]?.id ?? null;
}

/** SCREENS §5.6 method words. */
export function sspMethodLabel(method: SspMethod): string {
  return t(`policies.ssp.method.${method}`);
}

export function valueBasisLabel(basis: SspValueBasisAll): string {
  return t(`policies.ssp.basis.${basis}`);
}

// D-97 (3)/(3a) (SCREENS §11.4 rows 5 and 5a, rev 1.5): a series product's entry declares its E-49 basis, a
// PER_INCREMENT entry its E-125 quantity unit. The generated types carry both once ENG-C1b's API lands
// (sprint/l5 1434d07; 04 rev 1.17: E-49 PER_INCREMENT / PER_BOOKED_TERM, E-125 ssp_quantity_unit, T-REF-30
// quantity_unit); until then these local widenings mirror that contract, member for member.
/** E-49 with the two series bases (D-93 (4)). */
export type SspValueBasisAll = SspValueBasis | "PER_INCREMENT" | "PER_BOOKED_TERM";
/** The bases the editor offers, in E-49 order; identical to `VALUE_BASES` once it carries the series bases. */
export const EDITOR_BASES: readonly SspValueBasisAll[] = Array.from(
  new Set<SspValueBasisAll>([...VALUE_BASES, "PER_INCREMENT", "PER_BOOKED_TERM"]),
);
/** E-125 `ssp_quantity_unit`: what a series line's quantity counts for a PER_INCREMENT entry (D-97 (3)). */
export type SspQuantityUnit = "SERVICE_UNITS" | "INCREMENTS";
export const QUANTITY_UNITS: readonly SspQuantityUnit[] = ["SERVICE_UNITS", "INCREMENTS"];
/** API-S-SspEntry with the T-REF-30 members of 1434d07. */
export type SspEntryWithUnit = Omit<SspEntry, "value_basis"> & {
  readonly value_basis: SspValueBasisAll;
  readonly quantity_unit?: SspQuantityUnit | null;
};
/** API-S-SspEntry upsert body with the T-REF-30 members of 1434d07. */
export type SspEntryInputWithUnit = Omit<SspEntryInput, "value_basis"> & {
  readonly value_basis: SspValueBasisAll;
  readonly quantity_unit?: SspQuantityUnit | null;
};

export function quantityUnitLabel(unit: SspQuantityUnit): string {
  return t(`policies.ssp.quantityUnit.${unit}`);
}

/**
 * API-S-Product with the derived, read-only `requires_explicit_ssp_basis` ENG-C1b exposes (SSP-ADMISSION-R1;
 * SCREENS §11.4 row 5 rev 1.6): true when the product's default POB template version declares `series`
 * distinctness — the predicate the API's 422 applies. Typed locally until the regenerated schema carries it.
 */
export type ProductAdmission = {
  readonly code: string;
  readonly distinctness_default: Distinctness;
  readonly requires_explicit_ssp_basis?: boolean;
};

/**
 * Whether a new entry of `product` must declare its basis (no "Amount" default). The API's field decides;
 * while a payload predates it (undefined), the product's own `distinctness_default` = `series` stands in —
 * the bridge the lane record names, to be dropped once the field is always present.
 */
export function requiresExplicitBasis(product: ProductAdmission | undefined): boolean {
  if (product === undefined) {
    return false;
  }
  return product.requires_explicit_ssp_basis ?? product.distinctness_default === "series";
}

/** SCREENS §10.3 Distinctness words. */
export function sspDistinctnessLabel(distinctness: Distinctness): string {
  return t(`policies.ssp.distinctness.${distinctness}`);
}

export function resolutionLabel(mode: ResolutionMode): string {
  return t(`policies.sspBooks.resolution.${mode}`);
}

export function bandDimensionLabel(dimension: BandDimension): string {
  return t(`policies.sspVersion.bands.dimension.${dimension}`);
}

/** SCREENS §11.4 Scope: entity, currency, channel and segment joined; "All entities" without one. */
export function scopeText(book: SspBook): string {
  const parts = [
    book.entity_code ?? t("policies.sspBooks.allEntities"),
    book.currency,
    book.channel,
    book.segment,
  ].filter((part): part is string => part !== null && part !== "");
  return formatList(parts, "unit");
}

/** "2026-H1 · v1": the label (else `v<n>` alone) of a version summary. */
export function versionText(summary: {
  readonly legacy_version_label: string | null;
  readonly version_no: number;
}): string {
  const number = t("policies.version.number", { version: summary.version_no });
  return summary.legacy_version_label === null || summary.legacy_version_label === ""
    ? number
    : `${summary.legacy_version_label} · ${number}`;
}

/** The label of a version, else `v<n>`. */
export function versionLabel(version: SspBookVersion): string {
  return version.legacy_version_label === null || version.legacy_version_label === ""
    ? t("policies.version.number", { version: version.version_no })
    : version.legacy_version_label;
}

/** The band a grid row shows: the `NONE` band, else the first. */
export function primaryBand(entry: SspEntry): SspRange | null {
  return entry.ranges.find((band) => band.band_dimension === "NONE") ?? entry.ranges[0] ?? null;
}

/** The T-REF-30 key of an entry, as one string. */
export function entryKey(entry: {
  readonly product_code: string;
  readonly stratification: string;
  readonly region: string | null;
  readonly channel: string | null;
  readonly segment: string | null;
  readonly deal_size_band: string | null;
  readonly term_band: string | null;
  readonly currency: string;
}): string {
  return [
    entry.product_code,
    entry.stratification,
    entry.region ?? "",
    entry.channel ?? "",
    entry.segment ?? "",
    entry.deal_size_band ?? "",
    entry.term_band ?? "",
    entry.currency,
  ].join("\u001f");
}

function bandIn(band: SspRange): NonNullable<SspEntryInput["ranges"]>[number] {
  return {
    band_dimension: band.band_dimension,
    band_from: band.band_from,
    band_to: band.band_to,
    point_value: band.point_value,
    low_value: band.low_value,
    mid_value: band.mid_value,
    high_value: band.high_value,
  };
}

/**
 * The API-S-SspEntry upsert body of a stored entry with `changes` applied. A legacy range entry sends
 * no bands, because the server derives its `NONE` band (04 §16.4).
 */
export function entryInput(
  entry: SspEntry,
  changes: Partial<SspEntryInputWithUnit> = {},
): SspEntryInputWithUnit {
  const stored = entry as SspEntryWithUnit;
  const body: SspEntryInputWithUnit = {
    product_code: entry.product_code,
    stratification: entry.stratification,
    region: entry.region,
    channel: entry.channel,
    segment: entry.segment,
    deal_size_band: entry.deal_size_band,
    term_band: entry.term_band,
    currency: entry.currency,
    method: entry.method,
    value_basis: stored.value_basis,
    // D-97 (3): the declared unit round-trips through every edit of the entry; the API refuses a
    // PER_INCREMENT entry without it and never infers it.
    quantity_unit: stored.quantity_unit ?? null,
    unit_list_price: entry.unit_list_price,
    midpoint_discount_ratio: entry.midpoint_discount_ratio,
    range_ratio: entry.range_ratio,
    cost_basis: entry.cost_basis,
    margin_ratio: entry.margin_ratio,
    observable_point: entry.observable_point,
    revenue_account_code: entry.revenue_account_code,
    distinctness: entry.distinctness,
    ranges: entry.method === "legacy_range" ? null : entry.ranges.map(bandIn),
  };
  return { ...body, ...changes };
}

/** The `NONE` band of an entry replaced by `band` (inline edits of Low, Mid, High and Point). */
export function withPrimaryBand(entry: SspEntry, band: Partial<SspRange>): SspEntryInputWithUnit {
  const current = primaryBand(entry);
  const next = {
    ...(current ?? {
      band_dimension: "NONE" as const,
      band_from: null,
      band_to: null,
      point_value: null,
      low_value: null,
      mid_value: null,
      high_value: null,
    }),
    ...band,
  };
  const ranges =
    entry.ranges.length === 0 ? [next] : entry.ranges.map((r) => (r === current ? next : r));
  return entryInput(entry, { ranges: ranges.map(bandIn) });
}

export type EntryChangeKind = "added" | "removed" | "changed" | "unchanged";

/** The diff columns whose values can change between two versions of an entry. */
export const DIFF_FIELDS = ["method", "low", "mid", "high", "point", "distinctness"] as const;
export type DiffField = (typeof DIFF_FIELDS)[number];

export interface EntryDiffRow {
  readonly kind: EntryChangeKind;
  readonly entry: SspEntry;
  readonly before: SspEntry | null;
  readonly midChangeRatio: string | null;
  readonly changed: ReadonlySet<DiffField>;
}

/** The raw value of a diff column of an entry. */
export function diffValue(entry: SspEntry, field: DiffField): string | null {
  const band = primaryBand(entry);
  switch (field) {
    case "method":
      return entry.method;
    case "distinctness":
      return entry.distinctness;
    case "low":
      return band?.low_value ?? null;
    case "mid":
      return band?.mid_value ?? null;
    case "high":
      return band?.high_value ?? null;
    case "point":
      return band?.point_value ?? null;
  }
}

function sameDecimal(a: string | null, b: string | null): boolean {
  if (a === null || b === null) {
    return a === b;
  }
  const trim = (value: string) =>
    value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  return trim(a) === trim(b);
}

/**
 * SCREENS §11.4 Diff panel rows: the changed, added and removed entries of `GET …/diff`, then, with
 * `showUnchanged`, the version's other entries as unchanged, each in product order.
 */
export function diffRows(
  diff: SspVersionDiff,
  entries: readonly SspEntry[],
  showUnchanged: boolean,
): readonly EntryDiffRow[] {
  const rows: EntryDiffRow[] = [];
  for (const change of diff.changed) {
    const changed = new Set<DiffField>(
      DIFF_FIELDS.filter(
        (field) => !sameDecimal(diffValue(change.before, field), diffValue(change.after, field)),
      ),
    );
    rows.push({
      kind: "changed",
      entry: change.after,
      before: change.before,
      midChangeRatio: change.mid_change_ratio,
      changed,
    });
  }
  for (const entry of diff.added) {
    rows.push({ kind: "added", entry, before: null, midChangeRatio: null, changed: new Set() });
  }
  for (const entry of diff.removed) {
    rows.push({ kind: "removed", entry, before: null, midChangeRatio: null, changed: new Set() });
  }
  if (showUnchanged) {
    const listed = new Set(rows.map((row) => entryKey(row.entry)));
    for (const entry of entries) {
      if (!listed.has(entryKey(entry))) {
        rows.push({
          kind: "unchanged",
          entry,
          before: null,
          midChangeRatio: null,
          changed: new Set(),
        });
      }
    }
  }
  return rows.sort((a, b) =>
    a.entry.product_code === b.entry.product_code
      ? entryKey(a.entry).localeCompare(entryKey(b.entry))
      : a.entry.product_code.localeCompare(b.entry.product_code),
  );
}

/** The count of the Diff tab: changed, added and removed entries. */
export function diffCount(diff: SspVersionDiff): number {
  return diff.changed.length + diff.added.length + diff.removed.length;
}

/** The version a diff compares with: the current approved version, else (on the approved version
 * itself) the newest earlier approved or superseded version (L4-5-Q-53). */
export function diffBaselineId(
  book: SspBook,
  version: SspBookVersion,
  versions: readonly SspBookVersion[],
): string | null {
  const current = book.current_version;
  if (current !== null && current.id !== version.id) {
    return current.id;
  }
  const earlier = versions
    .filter(
      (item) =>
        item.version_no < version.version_no &&
        (item.status === "APPROVED" || item.status === "SUPERSEDED"),
    )
    .sort((a, b) => b.version_no - a.version_no);
  return earlier[0]?.id ?? null;
}

/** A null or empty text member as the em dash. */
export function textOrDash(value: string | null | undefined): string {
  return value === null || value === undefined || value === "" ? NO_VALUE : value;
}

const PERCENT_TEXT = /^(\d{1,3})(?:\.(\d{1,12}))?$/;

/**
 * A typed percent such as "15.00" as the API ratio "0.1500" (string arithmetic; DG-FE-08), or null
 * when the text is not a percent with at most three integer and twelve fraction digits.
 */
export function percentTextToRatio(text: string): string | null {
  const match = PERCENT_TEXT.exec(text.trim());
  if (match === null) {
    return null;
  }
  const integer = (match[1] ?? "0").padStart(3, "0");
  const whole = integer.slice(0, -2).replace(/^0+(?=\d)/, "");
  return `${whole}.${integer.slice(-2)}${match[2] ?? ""}`;
}

/** An API ratio such as "0.150000" as percent text for an input: "15.00", "12.3456". */
export function ratioToPercentText(ratio: string | null): string {
  const match = ratio === null ? null : /^(\d+)(?:\.(\d+))?$/.exec(ratio);
  if (match === null) {
    return "";
  }
  const fraction = (match[2] ?? "").padEnd(2, "0");
  const whole = `${match[1] ?? "0"}${fraction.slice(0, 2)}`.replace(/^0+(?=\d)/, "");
  const rest = fraction.slice(2).replace(/0+$/, "");
  return `${whole}.${rest.length >= 2 ? rest : rest.padEnd(2, "0")}`;
}
