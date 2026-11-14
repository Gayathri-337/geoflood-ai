import { describe, expect, it } from "vitest";
import { api, tokenStore } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

describe("progression endpoints", () => {
  it("asks for the progression of one event", async () => {
    tokenStore.set("tok");
    const fetchFn = mockFetch(() => fakeResponse(200, { series: [], unassigned: [] }));
    await api.progression(2);
    const [url, options] = fetchFn.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/events/2/progression");
    expect(options.method || "GET").toBe("GET");
    expect(options.headers.Authorization).toBe("Bearer tok");
  });

  it("sends the observation date with an upload only when there is one", async () => {
    const fetchFn = mockFetch(() => fakeResponse(201, { analysis_id: 1 }));
    await api.createAnalysis({ file: new File(["x"], "a.tif"), eventId: 1, sourceId: 1, acquiredAt: "2026-10-27" });
    await api.createAnalysis({ file: new File(["x"], "a.tif"), eventId: 1, sourceId: 1, acquiredAt: "" });
    await api.createAnalysis({ file: new File(["x"], "a.tif"), eventId: 1, sourceId: 1 });
    const [first, second, third] = fetchFn.mock.calls.map(([, options]) => options.body);
    expect(first.get("acquired_at")).toBe("2026-10-27");
    expect(second.has("acquired_at")).toBe(false);
    expect(third.has("acquired_at")).toBe(false);
  });
});
