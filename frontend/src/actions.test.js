import { describe, expect, it } from "vitest";
import {
  ACTION_TYPES, CLOSED, MAX_DESCRIPTION, MAX_TITLE, PRIORITIES, PRIORITY_BADGE, PRIORITY_COLOR, PRIORITY_LABEL,
  STATUSES, STATUS_BADGE, STATUS_LABEL, TYPE_LABEL, buildCreatePayload, emptyForm, isOverdue, nextStatuses,
  normalizePin, validateActionForm,
} from "./actions.js";

const valid = () => ({ ...emptyForm(), title: "Open a relief camp" });

describe("action vocabulary", () => {
  it("offers exactly the values the server accepts, each with a label and a colour", () => {
    expect(ACTION_TYPES.map((t) => t.value)).toEqual([
      "evacuation", "rescue", "shelter", "relief_distribution", "road_closure", "medical", "other",
    ]);
    expect(PRIORITIES.map((p) => p.value)).toEqual(["low", "medium", "high", "critical"]);
    expect(STATUSES.map((s) => s.value)).toEqual(["planned", "in_progress", "completed", "cancelled"]);
    for (const t of ACTION_TYPES) expect(TYPE_LABEL[t.value]).toBe(t.label);
    for (const p of PRIORITIES) {
      expect(PRIORITY_LABEL[p.value]).toBe(p.label);
      expect(PRIORITY_COLOR[p.value]).toMatch(/^#[0-9a-f]{6}$/);
      expect(PRIORITY_BADGE[p.value]).toBeTruthy();
    }
    for (const s of STATUSES) {
      expect(STATUS_LABEL[s.value]).toBe(s.label);
      expect(STATUS_BADGE[s.value]).toBeTruthy();
    }
    expect(new Set(Object.values(PRIORITY_COLOR)).size).toBe(4);
    expect(CLOSED.has("completed") && CLOSED.has("cancelled") && !CLOSED.has("planned")).toBe(true);
  });
});

describe("status changes", () => {
  it("offers sensible next steps and never the current status", () => {
    expect(nextStatuses("planned").map((n) => n.status)).toEqual(["in_progress", "completed", "cancelled"]);
    expect(nextStatuses("in_progress").map((n) => n.status)).toEqual(["completed", "cancelled"]);
    expect(nextStatuses("completed")).toEqual([{ status: "planned", label: "Reopen" }]);
    expect(nextStatuses("cancelled")).toEqual([{ status: "planned", label: "Reopen" }]);
    expect(nextStatuses("nonsense")).toEqual([]);
    for (const { value } of STATUSES) {
      expect(nextStatuses(value).some((n) => n.status === value)).toBe(false);
    }
  });

  it("uses button labels that do not clash with each other", () => {
    const labels = nextStatuses("planned").map((n) => n.label);
    expect(labels).toEqual(["Start", "Complete", "Cancel action"]);
  });
});

describe("overdue", () => {
  const now = new Date("2026-11-10T12:00:00Z");
  it("is true only for an open action whose due time has passed", () => {
    expect(isOverdue({ status: "planned", due_at: "2026-11-09T12:00:00Z" }, now)).toBe(true);
    expect(isOverdue({ status: "in_progress", due_at: "2026-11-10T11:59:59Z" }, now)).toBe(true);
    expect(isOverdue({ status: "planned", due_at: "2026-11-11T12:00:00Z" }, now)).toBe(false);
    expect(isOverdue({ status: "completed", due_at: "2026-11-01T12:00:00Z" }, now)).toBe(false);
    expect(isOverdue({ status: "cancelled", due_at: "2026-11-01T12:00:00Z" }, now)).toBe(false);
    expect(isOverdue({ status: "planned", due_at: null }, now)).toBe(false);
    expect(isOverdue({ status: "planned", due_at: "not a date" }, now)).toBe(false);
    expect(isOverdue(null, now)).toBe(false);
  });
});

describe("the new-action form", () => {
  it("starts with sensible, separate defaults every time", () => {
    const a = emptyForm();
    a.title = "changed";
    expect(emptyForm().title).toBe("");
    expect(emptyForm()).toEqual({
      title: "", action_type: "evacuation", priority: "medium", description: "", due: "", assignToMe: false,
    });
  });

  it("accepts a good form and refuses the usual mistakes", () => {
    expect(validateActionForm(valid())).toBe("");
    expect(validateActionForm({ ...valid(), title: "" })).toMatch(/Give the action a title/);
    expect(validateActionForm({ ...valid(), title: "     " })).toMatch(/Give the action a title/);
    expect(validateActionForm({ ...valid(), title: "x".repeat(MAX_TITLE) })).toBe("");
    expect(validateActionForm({ ...valid(), title: "x".repeat(MAX_TITLE + 1) })).toMatch(/at most 200/);
    expect(validateActionForm({ ...valid(), description: "x".repeat(MAX_DESCRIPTION) })).toBe("");
    expect(validateActionForm({ ...valid(), description: "x".repeat(MAX_DESCRIPTION + 1) })).toMatch(/at most 5000/);
    expect(validateActionForm({ ...valid(), due: "2026-13-45T99:99" })).toMatch(/not a valid date/);
    expect(validateActionForm({ ...valid(), due: "2026-11-20T09:00" })).toBe("");
    expect(validateActionForm({ ...valid(), action_type: "teleport" })).toMatch(/Choose the type/);
    expect(validateActionForm({ ...valid(), priority: "urgent" })).toMatch(/Choose a priority/);
  });

  it("builds the request body: trimmed text, nulls for what was left empty", () => {
    const body = buildCreatePayload({ ...valid(), title: "  Close the bridge ", description: "   " }, 7);
    expect(body).toEqual({
      title: "Close the bridge", action_type: "evacuation", priority: "medium", description: null,
      location: null, assigned_to: null, due_at: null,
    });
  });

  it("adds the pin, the assignee and the due time when they were chosen", () => {
    const form = { ...valid(), description: " Move families ", due: "2026-11-20T09:00", assignToMe: true };
    const body = buildCreatePayload(form, 7, { longitude: 93.7554, latitude: 26.5834 });
    expect(body.description).toBe("Move families");
    expect(body.location).toEqual({ longitude: 93.7554, latitude: 26.5834 });
    expect(body.assigned_to).toBe(7);
    expect(body.due_at).toBe(new Date("2026-11-20T09:00").toISOString());
    expect(buildCreatePayload({ ...form, assignToMe: true }, null).assigned_to).toBeNull();
    expect(buildCreatePayload({ ...form, assignToMe: false }, 7).assigned_to).toBeNull();
  });
});

describe("map pins", () => {
  it("rounds to 6 decimals", () => {
    expect(normalizePin(93.75543219, 26.58341987)).toEqual({ longitude: 93.755432, latitude: 26.58342 });
  });

  it("wraps a longitude that went round the world and limits the latitude", () => {
    expect(normalizePin(181, 10).longitude).toBe(-179);
    expect(normalizePin(-190, 10).longitude).toBe(170);
    expect(normalizePin(540.5, 10).longitude).toBe(-179.5);
    expect(normalizePin(93.7, 95).latitude).toBe(90);
    expect(normalizePin(93.7, -95).latitude).toBe(-90);
    expect(normalizePin(93.7, 26.5)).toEqual({ longitude: 93.7, latitude: 26.5 });
  });
});
