import { describe, expect, it } from "vitest";
import { api, tokenStore } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

describe("reference coverage endpoint", () => {
  it("asks for the coverage of one analysis, with the login token", async () => {
    tokenStore.set("tok");
    const fetchFn = mockFetch(() => fakeResponse(200, { level: "ok" }));
    await api.referenceCoverage(7);
    const [url, options] = fetchFn.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/analyses/7/reference-coverage");
    expect(options.headers.Authorization).toBe("Bearer tok");
  });
});
