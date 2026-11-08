import { describe, expect, it } from "vitest";
import { api, tokenStore } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

describe("upload and event endpoints", () => {
  it("sends the files as multipart form data and lets the browser set the content type", async () => {
    tokenStore.set("tok");
    const fetchFn = mockFetch(() => fakeResponse(201, { analysis_id: 1 }));
    await api.createAnalysis({
      file: new File(["x"], "a_S1Hand.tif"),
      baselineFile: new File(["y"], "a_JRCWaterHand.tif"),
      eventId: 2,
      sourceId: "1",
    });

    const [url, options] = fetchFn.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/analyses");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.headers["Content-Type"]).toBeUndefined();
    expect(options.headers.Authorization).toBe("Bearer tok");
    expect(options.body.get("file").name).toBe("a_S1Hand.tif");
    expect(options.body.get("baseline_file").name).toBe("a_JRCWaterHand.tif");
    expect(options.body.get("event_id")).toBe("2");
    expect(options.body.get("source_id")).toBe("1");
  });

  it("leaves the baseline out when there is none", async () => {
    const fetchFn = mockFetch(() => fakeResponse(201, { analysis_id: 1 }));
    await api.createAnalysis({ file: new File(["x"], "a.tif"), baselineFile: null, eventId: 1, sourceId: 1 });
    expect(fetchFn.mock.calls[0][1].body.has("baseline_file")).toBe(false);
  });

  it("calls the list endpoints", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, []));
    await api.events();
    await api.sources();
    const asKey = ([url, options]) => `${options.method} ${new URL(url).pathname}${new URL(url).search}`;
    expect(fetchFn.mock.calls.map(asKey)).toEqual(["GET /api/events?limit=100", "GET /api/sources"]);
  });

  it("creates an event with a JSON body", async () => {
    const fetchFn = mockFetch(() => fakeResponse(201, { event_id: 5 }));
    await api.createEvent({ name: "New flood", region_name: null, country: "India" });
    const [, options] = fetchFn.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ name: "New flood", region_name: null, country: "India" });
  });
});
