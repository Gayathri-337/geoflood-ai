import { describe, expect, it } from "vitest";
import { api } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

describe("severity endpoints", () => {
  it("reads with GET and saves with POST", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.severity(2);
    await api.saveSeverity(2);
    const asKey = ([url, options]) => `${options.method} ${new URL(url).pathname}`;
    expect(fetchFn.mock.calls.map(asKey)).toEqual(["GET /api/analyses/2/severity", "POST /api/analyses/2/severity"]);
  });
});
