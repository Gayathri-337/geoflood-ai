import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { ACTIONS, EVENT, EVENT_ANALYSES, PINS } from "../eventFixtures.js";
import { PROGRESSION } from "../progressionFixtures.js";
import { USER, mockApi } from "../testUtils.js";
import EventPage from "./EventPage.jsx";

vi.mock("../map/EventMap.jsx", async () => {
  const React = await import("react");
  return { default: () => React.createElement("div", { "data-testid": "map-stub" }) };
});

const ROUTES = {
  "GET /api/events/2": [200, EVENT],
  "GET /api/analyses?event_id=2&limit=50": [200, EVENT_ANALYSES],
  "GET /api/events/2/actions?limit=200": [200, ACTIONS],
  "GET /api/events/2/actions/geojson": [200, PINS],
  "GET /api/events/2/progression": [200, PROGRESSION],
};

function renderPage(role) {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/events/2"]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("event page: change over time", () => {
  it.each(["viewer", "analyst", "admin"])("shows the comparison to a %s", async (role) => {
    mockApi(ROUTES);
    renderPage(role);
    await screen.findByTestId("map-stub");
    expect(await screen.findByRole("img", { name: /detected water area in km²/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /change over time/i })).toBeInTheDocument();
  });

  it("still shows the event and its actions when the comparison fails", async () => {
    mockApi({ ...ROUTES, "GET /api/events/2/progression": [500, { detail: "boom" }] });
    renderPage("analyst");
    await screen.findByTestId("map-stub");
    expect(await screen.findByText(/could not be loaded just now/)).toBeInTheDocument();
    expect(screen.getByText("Evacuate the school")).toBeInTheDocument();
  });
});
