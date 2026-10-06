// Legal entities (04 API-R-17 `GET, POST /entities`, `GET, PATCH /entities/{id}` with `If-Match`,
// `PUT /entities/{id}/books/{code}`; §16.4 API-S-Entity; T-REF-01, T-REF-03 `entity_book`; E-02 books;
// BR-REF-01; REQ-REF-001, REQ-BK-001, REQ-ENT-001; SCREENS_B §9.2; BUILD_SPEC RFD-18). The entity
// grid, the lookup of every entity (parents, "Used by" currencies) and the entity drawer's commands.
// The context-pill reads stay in `tenant.ts`.
import { useQuery } from "@tanstack/react-query";

import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { type Book, type BookCode, type Entity, ENTITIES_PATH, STRUCTURE_LIMIT } from "./tenant";

export type EntityCreate = components["schemas"]["EntityIn"];
export type EntityUpdate = components["schemas"]["EntityUpdateIn"];
export type EntityBook = components["schemas"]["EntityBookOut"];
export type EntityBookUpdate = components["schemas"]["EntityBookIn"];

/** SCREENS RT-75 SF-15:entities. */
export const ENTITIES_ROUTE = "/settings/entities";
/** 04 API-R-17 rev 1.2: create and edit need any of these. */
export const ENTITY_MAINTAIN_PERMISSIONS: readonly string[] = [
  "masterdata.maintain",
  "settings.manage",
];
/** SCREENS_B §9.2 "Code" rule: "Use letters, digits and hyphens." */
export const ENTITY_CODE_PATTERN = /^[A-Za-z0-9-]+$/;
/** E-02 book codes in 04 order. */
export const BOOK_CODES: readonly BookCode[] = ["ASC606", "IFRS15", "LEGACY"];
/** The default entity sort (API-R-17: code). */
export const DEFAULT_ENTITY_SORT = "code";

/** Every entity read, for invalidation after a command (includes the context pill's list). */
export const EVERY_ENTITY: QueryKey = queryKey("entities", "tenant");

export function entitiesGridKey(): QueryKey {
  return queryKey("entities", "tenant", { view: "grid" });
}

export function fetchEntitiesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Entity>> {
  return fetchListPage<Entity>(ENTITIES_PATH, { sort: sort ?? DEFAULT_ENTITY_SORT }, cursor);
}

export function allEntitiesKey(): QueryKey {
  return queryKey("entities", "tenant", { view: "all" });
}

/** Every entity, active or not, in code order: parents, calendar users and currency users. */
export async function fetchAllEntities(): Promise<readonly Entity[]> {
  const page = await fetchListPage<Entity>(ENTITIES_PATH, { sort: DEFAULT_ENTITY_SORT }, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useAllEntities(enabled = true) {
  return useQuery({ queryKey: allEntitiesKey(), queryFn: fetchAllEntities, enabled });
}

export function entityPath(entityId: string): string {
  return `${ENTITIES_PATH}/${entityId}`;
}

export function entityBookPath(entityId: string, code: BookCode): string {
  return `${entityPath(entityId)}/books/${code}`;
}

/** SCREENS_B §9.2 book labels: "ASC 606", "IFRS 15", "Legacy". */
export function bookLabel(code: BookCode, books: readonly Book[] = []): string {
  const named = books.find((book) => book.code === code)?.name;
  if (named !== undefined) {
    return named;
  }
  switch (code) {
    case "ASC606":
      return "ASC 606";
    case "IFRS15":
      return "IFRS 15";
    case "LEGACY":
      return "Legacy";
  }
}

/** The enabled books of an entity in E-02 order, labelled. */
export function enabledBookLabels(entity: Entity, books: readonly Book[] = []): readonly string[] {
  return BOOK_CODES.filter((code) =>
    entity.books.some((row) => row.book_code === code && row.is_enabled),
  ).map((code) => bookLabel(code, books));
}

/** The entity book row of a code, if the entity has one. */
export function entityBook(entity: Entity, code: BookCode): EntityBook | null {
  return entity.books.find((row) => row.book_code === code) ?? null;
}

/** The codes of the entities whose functional currency is `currency` (SCREENS_B §9.4 "Used by"). */
export function entitiesUsing(entities: readonly Entity[], currency: string): readonly string[] {
  return entities
    .filter((entity) => entity.functional_currency === currency)
    .map((entity) => entity.code);
}
