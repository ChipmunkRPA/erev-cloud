// The date contract of mocked traffic (`./contract`, `./msw`; supervisor ruling R-65): a date-only
// string under a `date-time` member, in a response or in a request body, is a violation; the shape
// the API sends is not; and `installMswServer` reads what the handlers of a test exchange.
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { contractViolations } from "./contract";
import { installMswServer, mockedTrafficViolations, server } from "./msw";

installMswServer();

const ORIGIN = "http://localhost";

function policies(effectiveFrom: string | null): string {
  return JSON.stringify({
    items: [{ id: "p1", effective_from: effectiveFrom }],
    next_cursor: null,
  });
}

describe("contractViolations", () => {
  it("reports a date-only string under a date-time member of a response", () => {
    expect(
      contractViolations({
        method: "GET",
        url: `${ORIGIN}/api/v1/policies?limit=200`,
        status: 200,
        body: policies("2023-01-01"),
      }),
    ).toEqual([
      'GET /api/v1/policies -> 200: .items[].effective_from "2023-01-01" is not a date-time (RFC 3339 with an offset)',
    ]);
  });

  it("accepts the instant the API sends, and null", () => {
    for (const value of ["2023-01-01T12:00:00Z", "2023-01-01T12:00:00.123456+00:00", null]) {
      expect(
        contractViolations({
          method: "GET",
          url: `${ORIGIN}/api/v1/policies`,
          status: 200,
          body: policies(value),
        }),
      ).toEqual([]);
    }
  });

  it("reports a date-only string under a date-time member of a request body", () => {
    expect(
      contractViolations({
        method: "POST",
        url: `${ORIGIN}/api/v1/sod-exceptions`,
        body: JSON.stringify({ valid_from: "2026-09-19", valid_to: "2027-09-19T23:59:59Z" }),
      }),
    ).toEqual([
      'request POST /api/v1/sod-exceptions: .valid_from "2026-09-19" is not a date-time (RFC 3339 with an offset)',
    ]);
  });

  it("reports an instant under a date member", () => {
    expect(
      contractViolations({
        method: "GET",
        url: `${ORIGIN}/api/v1/contracts/5b7e0c9a-1d2f-4c3b-9a8e-6f5d4c3b2a10?book=ASC606`,
        status: 200,
        body: JSON.stringify({
          inception_date: "2026-01-01T00:00:00Z",
          signature_date: "2026-01-01",
        }),
      }),
    ).toEqual([
      'GET /api/v1/contracts/{contract_id} -> 200: .inception_date "2026-01-01T00:00:00Z" is not a date (YYYY-MM-DD)',
    ]);
  });

  it("checks nothing the OpenAPI document does not describe", () => {
    const body = JSON.stringify({ effective_from: "yesterday" });
    expect(
      contractViolations({ method: "GET", url: `${ORIGIN}/api/v1/probe`, status: 200, body }),
    ).toEqual([]);
    expect(
      contractViolations({ method: "GET", url: `${ORIGIN}/api/v1/policies`, status: 418, body }),
    ).toEqual([]);
    expect(
      contractViolations({
        method: "GET",
        url: `${ORIGIN}/api/v1/policies`,
        status: 200,
        body: "not json",
      }),
    ).toEqual([]);
  });
});

describe("installMswServer", () => {
  it("reads the requests and the mocked responses of a test", async () => {
    server.use(
      http.post(`${ORIGIN}/api/v1/sod-exceptions`, () =>
        HttpResponse.json(
          { id: "e1", valid_from: "2026-09-19", valid_to: "2027-09-19T23:59:59Z" },
          { status: 201 },
        ),
      ),
    );
    await fetch(`${ORIGIN}/api/v1/sod-exceptions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valid_from: "2026-09-19T00:00:00Z", valid_to: "2027-09-19" }),
    });

    // Drained here, so the hook of this file finds nothing; undrained, it fails the test.
    expect((await mockedTrafficViolations()).sort()).toEqual([
      'POST /api/v1/sod-exceptions -> 201: .valid_from "2026-09-19" is not a date-time (RFC 3339 with an offset)',
      'request POST /api/v1/sod-exceptions: .valid_to "2027-09-19" is not a date-time (RFC 3339 with an offset)',
    ]);
  });
});
