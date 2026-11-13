import { describe, expect, it, vi } from "vitest";
import { PRIORITY_COLOR } from "../actions.js";
import { onEachPin, pinToLayer } from "./pins.js";

describe("action pins", () => {
  it("colours a pin by priority and fades it once the action is closed", () => {
    const open = pinToLayer({ properties: { priority: "critical", status: "planned" } }, [26.5, 93.7]);
    const done = pinToLayer({ properties: { priority: "critical", status: "completed" } }, [26.5, 93.7]);
    expect(open.options.fillColor).toBe(PRIORITY_COLOR.critical);
    expect(done.options.fillOpacity).toBeLessThan(open.options.fillOpacity);
    expect(pinToLayer({ properties: { priority: "weird", status: "planned" } }, [1, 2]).options.fillColor).toBe("#6c757d");
    expect(pinToLayer({}, [1, 2]).options.fillColor).toBe("#6c757d");
    expect(open.getLatLng().lat).toBe(26.5);
    expect(open.getLatLng().lng).toBe(93.7);
  });

  it("binds a popup made of text only", () => {
    const layer = { bindPopup: vi.fn() };
    onEachPin(
      { properties: { title: '<img src=x onerror="alert(1)">', action_type: "road_closure", priority: "high", status: "planned" } },
      layer,
    );
    const popup = layer.bindPopup.mock.calls[0][0];
    expect(popup.querySelector("img")).toBeNull();
    expect(popup.textContent).toContain("<img src=x");
    for (const text of ["Road closure", "High", "Planned"]) expect(popup.textContent).toContain(text);
  });
});
