// @vitest-environment jsdom
// The access-limited state (SCREENS §0.6 SCR-PERM-01 and SCR-PERM-02 (c), rev 1.71; §0.7 SCR-ST-06):
// the description names the permission by its phrase and, in parentheses and in mono, by its code.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { accessDescription, accessDescriptionCodes } from "../../test/access";
import { AccessLimited } from "./AccessLimited";

afterEach(() => {
  cleanup();
});

describe("the access-limited state", () => {
  it("a member without the permission is told what to ask for: the phrase, and the code in mono", () => {
    render(<AccessLimited area="Security" permissions={["settings.manage"]} />);

    expect(
      screen.getByRole("heading", { level: 2, name: "You do not have access to Security" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes managing workspace settings (settings.manage).",
    );
    expect(accessDescriptionCodes()).toEqual(["settings.manage"]);
  });

  it("a page that any of two permissions opens names both", () => {
    render(
      <AccessLimited
        area="API clients and webhooks"
        permissions={["api_client.manage", "webhook.manage"]}
      />,
    );

    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes managing API clients (api_client.manage) or managing webhooks (webhook.manage).",
    );
    expect(accessDescriptionCodes()).toEqual(["api_client.manage", "webhook.manage"]);
  });

  it("a holder for named entities reads the page's sentence of the whole workspace, with the permission it names", () => {
    render(
      <AccessLimited
        area="API clients and webhooks"
        permissions={["api_client.manage", "webhook.manage"]}
        allEntities={{ message: "developer.access.allEntities", permission: "webhook.manage" }}
      />,
    );

    expect(accessDescription()).toBe(
      "Webhooks cover every entity of the workspace. Ask a workspace administrator for a role that includes managing webhooks (webhook.manage) for all entities.",
    );
    expect(accessDescriptionCodes()).toEqual(["webhook.manage"]);
  });
});
