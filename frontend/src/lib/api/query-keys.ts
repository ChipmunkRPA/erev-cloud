// Query keys `[resource, scope, params]` (docs/dev-guide.md DG-FE-04). `scope` names whose data a key
// holds: "public" before sign-in, "session" for the signed-in user, "tenant" for the active
// workspace. Invalidating `[resource]` covers every scope and parameter set of that resource.
export type QueryScope = "public" | "session" | "tenant";
export type QueryParams = Readonly<Record<string, string | number | boolean | null>>;
export type QueryKey = readonly [resource: string, scope: QueryScope, params: QueryParams];

export function queryKey(resource: string, scope: QueryScope, params: QueryParams = {}): QueryKey {
  return [resource, scope, params];
}

export const queryKeys = {
  session: (): QueryKey => queryKey("session", "public"),
  me: (): QueryKey => queryKey("me", "session"),
  job: (jobId: string): QueryKey => queryKey("jobs", "tenant", { id: jobId }),
};
