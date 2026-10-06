// What the signed-in member may do, and for which legal entities (SCREENS §0.6 SCR-PERM-01 and -02,
// rev 1.30; dev-guide DG-FE-16, rev 1.175; BR-UX-05; 04 §16.12 API-S-Me `permission_scopes`, T-PLT-10;
// dev-guide DG-KRN-AUTH-04). This is the one module that reads `permissions` and `permission_scopes`
// of `GET /me`: a role is granted for all entities or for named ones, so "is the code among
// `permissions`" does not say whether a command may be used on the record in front of the member.
//
// A gate asks one of four questions, the ones the API asks:
// - `holds(permission, entity)`: a record of one legal entity — a contract, a period, an import, a
//   journal run. Held for that entity.
// - `holdsAnywhere(permission)`: a tenant-wide object — a policy, a product, a customer — and a route.
//   Held for at least one entity.
// - `holdsForAll(permission)`: a tenant-wide act or list — the definition of a role, a list of the
//   whole workspace. Held for all entities.
// - `holdsForEvery(permission, entities)`: a membership or a role assignment. Held for every entity
//   its grants name, and for all entities when one of them is for all.
//
// The API stays the enforcer; a gate only keeps a command the API would refuse from being offered.
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { type Me, useMe } from "./api/queries/me";
import { entitiesKey, fetchActiveEntities } from "./api/queries/tenant";

/** A legal entity as a record states it: by id, by code, or both. The id decides when both are given. */
export interface EntityOf {
  readonly id?: string | null | undefined;
  readonly code?: string | null | undefined;
}

/** The entities a permission is held for: all of them, or the ids of the named ones. */
export type Scope = "*" | readonly string[];

export interface Access {
  /** Held for the entity of a record; `null` or `undefined` is a tenant-wide object (held anywhere). */
  readonly holds: (permission: string, entity: EntityOf | null | undefined) => boolean;
  /** Held for at least one entity. */
  readonly holdsAnywhere: (permission: string) => boolean;
  /** Held for all entities. */
  readonly holdsForAll: (permission: string) => boolean;
  /** Held for every entity of the list; `"*"` is a grant for all entities. */
  readonly holdsForEvery: (permission: string, entities: readonly EntityOf[] | "*") => boolean;
  /** The entities the permission is held for, or null when it is not held. */
  readonly scope: (permission: string) => Scope | null;
}

type Granted = Pick<Me, "permissions" | "permission_scopes">;

/**
 * The access of a member. `entities` are the legal entities of the workspace the session sees: they
 * resolve a record that states its entity by code alone. Without them a member of named entities
 * holds nothing for such a record — the command is not offered rather than offered and refused.
 */
export function accessOf(
  me: Granted | undefined,
  entities: readonly { readonly id: string; readonly code: string }[] = [],
): Access {
  const scopes = new Map<string, Scope>();
  if (me !== undefined) {
    const held = new Set(me.permissions);
    for (const [permission, scope] of Object.entries(me.permission_scopes)) {
      if (held.has(permission) && (scope === "*" || scope.length > 0)) {
        scopes.set(permission, scope);
      }
    }
  }
  const idOf = new Map(entities.map((entity) => [entity.code, entity.id]));
  const within = (scope: Scope, entity: EntityOf): boolean => {
    if (scope === "*") {
      return true;
    }
    const id = entity.id ?? (entity.code == null ? undefined : idOf.get(entity.code));
    return id != null && scope.includes(id);
  };
  const scope = (permission: string): Scope | null => scopes.get(permission) ?? null;
  return {
    holds: (permission, entity) => {
      const found = scope(permission);
      return found !== null && (entity == null || within(found, entity));
    },
    holdsAnywhere: (permission) => scope(permission) !== null,
    holdsForAll: (permission) => scope(permission) === "*",
    holdsForEvery: (permission, named) => {
      const found = scope(permission);
      if (found === null) {
        return false;
      }
      return named === "*" ? found === "*" : named.every((entity) => within(found, entity));
    },
    scope,
  };
}

/**
 * The access of the signed-in member. A member of all entities needs no entity read; for a member of
 * named entities the entities of the workspace are read under the context bar's key, so the two share
 * one request.
 */
export function useAccess(): Access {
  const me = useMe().data;
  const named =
    me !== undefined && Object.values(me.permission_scopes).some((scope) => scope !== "*");
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: named,
  }).data;
  return useMemo(() => accessOf(me, entities), [me, entities]);
}
