// The signed-in user (04 API-R-03, §16.12 API-S-Me): memberships, permissions, preferences, tenant
// settings and the engine release, from `GET /me`; `PATCH /me/preferences` changes display
// preferences, and a success writes the answered preferences into the cached `/me`.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api, unwrap } from "../client";
import { type CommandOutcome, useCommand } from "../commands";
import { queryKeys } from "../query-keys";
import type { components } from "../schema";

export type Me = components["schemas"]["MeOut"];
export type MeMembership = components["schemas"]["MeMembershipOut"];
export type EngineRelease = components["schemas"]["EngineReleaseOut"];
export type Preferences = components["schemas"]["PreferencesOut"];
export type PreferencesPatch = components["schemas"]["PreferencesIn"];
type PreferencesUpdated = components["schemas"]["PreferencesUpdateOut"];

export const PREFERENCES_PATH = "/api/v1/me/preferences";

export function fetchMe(): Promise<Me> {
  return unwrap(api.GET("/api/v1/me"));
}

export function useMe() {
  return useQuery({ queryKey: queryKeys.me(), queryFn: fetchMe });
}

export interface PreferencesCommand {
  readonly update: (patch: PreferencesPatch) => Promise<CommandOutcome<PreferencesUpdated>>;
  readonly pending: boolean;
}

export function useUpdatePreferences(): PreferencesCommand {
  const queryClient = useQueryClient();
  const { submit, pending } = useCommand<PreferencesUpdated>({
    method: "PATCH",
    path: PREFERENCES_PATH,
  });
  const update = useCallback(
    async (patch: PreferencesPatch) => {
      const outcome = await submit(patch);
      if (outcome.kind === "succeeded" && outcome.data !== null) {
        const { preferences } = outcome.data;
        queryClient.setQueryData<Me>(queryKeys.me(), (me) =>
          me === undefined ? me : { ...me, preferences },
        );
      }
      return outcome;
    },
    [queryClient, submit],
  );
  return { update, pending };
}
