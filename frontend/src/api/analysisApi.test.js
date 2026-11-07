import { describe, expect, it } from "vitest";
import { api } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

const asKey = ([url, options]) => {
  const u = new URL(url);
  return `${options.method} ${u.pathname}${u.search}`;
};

describe("analysis endpoints", () => {
  it("calls the expected addresses", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.analysis(2);
    await api.zones(2);
    await api.impactSummary(2);
    await api.impactLayer(2, "roads");
    await api.computeImpact(2, 300);
    expect(fetchFn.mock.calls.map(asKey)).toEqual([
      "GET /api/analyses/2",
      "GET /api/analyses/2/zones",
      "GET /api/analyses/2/impact",
      "GET /api/analyses/2/impact/roads",
      "POST /api/analyses/2/impact?near_m=300",
    ]);
  });

  it("does not let an odd id change the address", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.analysis("2/../../users");
    expect(new URL(fetchFn.mock.calls[0][0]).pathname).toBe("/api/analyses/2%2F..%2F..%2Fusers");
  });
});