// Subledger lines (04 API-R-36 `GET /subledger-lines`, API-S-SubledgerLine, E-15 account roles; SCREENS
// §4.5; BUILD_SPEC CTR-23). The SF-03:journals grid reads the contract's lines in the context book recorded
// by `known_at`, 200 lines a page. API-R-36 sorts by `id` (default `-id`) or `recorded_at` only, so the
// grid keeps the server order and the Period column is not sortable (L5-4-Q-50). Amounts are signed by
// side (debit positive, credit negative); the grid shows each side as the absolute amount (DS-FMT-06).
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type SubledgerLine = components["schemas"]["SubledgerLineOut"];
export type AccountRole = components["schemas"]["AccountRole"];

export const SUBLEDGER_LINES_PATH = "/api/v1/subledger-lines";
/** SCREENS SCR-IA-07 screen code of the journal lines grid's saved views. */
export const JOURNAL_LINES_SCREEN_CODE = "SF-03:journals";

/** E-15 `account_role` literals in the 04 enumeration order (the Account role filter). */
export const ACCOUNT_ROLES: readonly AccountRole[] = [
  "REVENUE",
  "CONTRACT_LIABILITY",
  "CONTRACT_ASSET",
  "UNBILLED_RECEIVABLE",
  "ACCOUNTS_RECEIVABLE",
  "BILLING_CLEARING",
  "REFUND_LIABILITY",
  "RETURN_ASSET",
  "DEPOSIT_LIABILITY",
  "CONSIDERATION_PAYABLE",
  "CUSTOMER_INCENTIVE_ASSET",
  "COST_TO_OBTAIN_ASSET",
  "COST_TO_FULFILL_ASSET",
  "CONTRACT_COST_AMORTIZATION",
  "CONTRACT_COST_IMPAIRMENT",
  "LOSS_PROVISION",
  "LOSS_EXPENSE",
  "WARRANTY_PROVISION",
  "WARRANTY_EXPENSE",
  "INTEREST_INCOME",
  "INTEREST_EXPENSE",
  "FX_GAIN_LOSS",
  "INTERCOMPANY_DUE_TO",
  "INTERCOMPANY_DUE_FROM",
  "NONCASH_CONSIDERATION_ASSET",
  "SALES_TAX_PAYABLE",
  "PRE_STANDARD_REVENUE",
  "ROUNDING",
  "COST_OF_REVENUE",
  "CONTRACT_COST_CLEARING",
  "RECEIVABLE_CONTRA",
  "RETAINED_EARNINGS",
  "FINANCING_OBLIGATION",
];

/** The API parameters of one journal lines grid state (SCREENS §4.5 filters and context). */
export interface JournalLineQuery {
  readonly contractId: string;
  readonly book: string | null;
  readonly knownAt: string | null;
  readonly period: string | null;
  readonly originPeriod: string | null;
  readonly accountRole: string | null;
}

export function subledgerLinesKey(query: JournalLineQuery): QueryKey {
  return queryKey("subledger-lines", "tenant", {
    contract: query.contractId,
    book: query.book,
    known_at: query.knownAt,
    period: query.period,
    origin_period: query.originPeriod,
    account_role: query.accountRole,
  });
}

/** One page of the contract's subledger lines. */
export function fetchSubledgerLinesPage(
  query: JournalLineQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SubledgerLine>> {
  return fetchListPage<SubledgerLine>(
    SUBLEDGER_LINES_PATH,
    {
      contract: query.contractId,
      book: query.book,
      known_at: query.knownAt,
      period: query.period,
      origin_period: query.originPeriod,
      account_role: query.accountRole,
      sort,
    },
    cursor,
  );
}

/** SCREENS §4.5 columns 8 and 9: the absolute amount of the line's side, else null. */
export function sideAmount(line: SubledgerLine, side: "D" | "C"): string | null {
  if (line.dr_cr !== side) {
    return null;
  }
  const value = line.amount_txn.amount;
  return value.startsWith("-") ? value.slice(1) : value;
}

/** SCREENS §4.5 column 12: a void reversal or a netting reclass reversal. */
export function reversesLine(line: SubledgerLine): boolean {
  return line.posting_kind === "VOID_REVERSAL" || line.entry_kind === "NETTING_RECLASS_REVERSAL";
}
