import { describe, expect, it } from "vitest";
import { api } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

const asKey = ([url, options]) => {
  const u = new URL(url);
  return `${options.method} ${u.pathname}${u.search}`;
};

describe("event and action endpoints", () => {
  it("calls the expected addresses, with the filters in a fixed order", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.event(2);
    await api.analysesForEvent(2);
    await api.eventActions(2);
    await api.eventActions(2, { status: "planned", priority: "high" });
    await api.eventActions(2, { status: "", priority: "" });
    await api.actionPins(2);
    expect(fetchFn.mock.calls.map(asKey)).toEqual([
      "GET /api/events/2",
      "GET /api/analyses?event_id=2&limit=50",
      "GET /api/events/2/actions?limit=200",
      "GET /api/events/2/actions?limit=200&status=planned&priority=high",
      "GET /api/events/2/actions?limit=200",
      "GET /api/events/2/actions/geojson",
    ]);
  });

  it("creates, changes and deletes actions", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.createAction(2, { title: "T", action_type: "other" });
    await api.updateAction(5, { status: "completed" });
    await api.deleteAction(5);
    const [create, update, remove] = fetchFn.mock.calls;
    expect(asKey(create)).toBe("POST /api/events/2/actions");
    expect(JSON.parse(create[1].body)).toEqual({ title: "T", action_type: "other" });
    expect(create[1].headers["Content-Type"]).toBe("application/json");
    expect(asKey(update)).toBe("PATCH /api/actions/5");
    expect(JSON.parse(update[1].body)).toEqual({ status: "completed" });
    expect(asKey(remove)).toBe("DELETE /api/actions/5");
    expect(remove[1].body).toBeUndefined();
  });

  it("does not let an odd id change the address", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.deleteAction("5/../../users");
    expect(new URL(fetchFn.mock.calls[0][0]).pathname).toBe("/api/actions/5%2F..%2F..%2Fusers");
  });
});
