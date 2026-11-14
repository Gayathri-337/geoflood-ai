import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { ACTIONS, EVENT, EVENT_ANALYSES, PINS } from "../eventFixtures.js";
import { USER, callsTo, mockApi } from "../testUtils.js";
import EventPage from "./EventPage.jsx";

vi.mock("../map/EventMap.jsx", async () => {
  const React = await import("react");
  return {
    default: (props) =>
      React.createElement(
        "div",
        {
          "data-testid": "map-stub",
          "data-bounds": JSON.stringify(props.bounds),
          "data-pins": String(props.pins?.features?.length ?? 0),
          "data-picking": String(props.picking),
          "data-picked": props.picked ? `${props.picked.longitude},${props.picked.latitude}` : "",
        },
        React.createElement("button", { type: "button", onClick: () => props.onPick(93.7554, 26.5834) }, "stub: click map"),
      ),
  };
});

const LIST = "GET /api/events/2/actions?limit=200";
const ROUTES = {
  "GET /api/events/2": [200, EVENT],
  "GET /api/analyses?event_id=2&limit=50": [200, EVENT_ANALYSES],
  [LIST]: [200, ACTIONS],
  "GET /api/events/2/actions/geojson": [200, PINS],
  "GET /api/events/2/progression": [200, { event_id: 2, series: [], unassigned: [], criteria: {}, note: "" }],
};

function renderPage(role = "analyst", path = "/events/2") {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventPage />} />
          <Route path="/events" element={<div>events list</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
const item = (id) => within(screen.getByTestId(`action-${id}`));
const body = (fetchFn, key) => JSON.parse(callsTo(fetchFn, key)[0][1].body);
const ready = () => screen.findByTestId("map-stub");

describe("event page", () => {
  it("loads the event, its analyses, its actions and its pins", async () => {
    const fetchFn = mockApi(ROUTES);
    renderPage();
    expect(await screen.findByRole("heading", { name: "Assam flood demo" })).toBeInTheDocument();
    expect(screen.getByText(/Brahmaputra valley, India/)).toBeInTheDocument();
    
    for (const key of Object.keys(ROUTES)) {
      await vi.waitFor(() => {
        expect(callsTo(fetchFn, key)).toHaveLength(1);
      });
    }

    expect(screen.getAllByTestId(/^action-/)).toHaveLength(3);
    const map = await ready();
    expect(map.dataset.pins).toBe("2");
    expect(JSON.parse(map.dataset.bounds)).toEqual([[26.0325, 92.8614], [26.6304, 93.7812]]);
    expect(screen.getByRole("link", { name: "Analysis 4: India_747992_S1Hand.tif" })).toHaveAttribute("href", "/analyses/4");
    expect(screen.getByText("Severe")).toBeInTheDocument();
  });

  it("asks the server for the filtered list when a filter changes", async () => {
    const fetchFn = mockApi({ ...ROUTES, [`${LIST}&status=planned`]: [200, [ACTIONS[0]]] });
    renderPage();
    await ready();
    await userEvent.setup().selectOptions(screen.getByLabelText(/filter by status/i), "planned");

    await vi.waitFor(() => expect(screen.getAllByTestId(/^action-/)).toHaveLength(1));
    expect(callsTo(fetchFn, `${LIST}&status=planned`)).toHaveLength(1);
    expect(screen.queryByText("Close the NH129 bridge")).toBeNull();
  });

  it("lets an analyst add an action with a pin picked on the map", async () => {
    const fetchFn = mockApi({ ...ROUTES, "POST /api/events/2/actions": [201, { ...ACTIONS[0], action_id: 13 }] });
    renderPage("analyst");
    const user = userEvent.setup();
    await ready();

    await user.click(screen.getByRole("button", { name: /add action/i }));
    await user.type(screen.getByLabelText(/^title$/i), "  Set up a medical camp ");
    await user.selectOptions(screen.getByLabelText(/^type$/i), "medical");
    await user.selectOptions(screen.getByLabelText(/^priority$/i), "high");
    await user.click(screen.getByLabelText(/assign to me/i));

    await user.click(screen.getByRole("button", { name: /pick on map/i }));
    expect(screen.getByTestId("map-stub")).toHaveAttribute("data-picking", "true");
    await user.click(screen.getByRole("button", { name: /stub: click map/i }));
    expect(screen.getByTestId("map-stub")).toHaveAttribute("data-picked", "93.7554,26.5834");
    expect(screen.getByTestId("map-stub")).toHaveAttribute("data-picking", "false");
    expect(screen.getByTestId("pin-text")).toHaveTextContent("Pin at 26.5834, 93.7554");

    await user.click(screen.getByRole("button", { name: /save action/i }));
    await vi.waitFor(() => expect(callsTo(fetchFn, LIST)).toHaveLength(2)); // the list was reloaded
    expect(body(fetchFn, "POST /api/events/2/actions")).toEqual({
      title: "Set up a medical camp", action_type: "medical", priority: "high", description: null,
      location: { longitude: 93.7554, latitude: 26.5834 }, assigned_to: 1, due_at: null,
    });
    await vi.waitFor(() => expect(screen.getByTestId("map-stub")).toHaveAttribute("data-picked", ""));
    expect(screen.getByLabelText(/^title$/i)).toHaveValue("");
  });

  it("shows the server's message in the form and keeps what was typed", async () => {
    mockApi({ ...ROUTES, "POST /api/events/2/actions": [422, { detail: "The person to assign does not exist or is disabled." }] });
    renderPage("analyst");
    const user = userEvent.setup();
    await ready();
    await user.click(screen.getByRole("button", { name: /add action/i }));
    await user.type(screen.getByLabelText(/^title$/i), "Open the shelter");
    await user.click(screen.getByRole("button", { name: /save action/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("does not exist or is disabled");
    expect(screen.getByLabelText(/^title$/i)).toHaveValue("Open the shelter");
  });

  it("gives a viewer the list and the map but no way to change anything", async () => {
    mockApi(ROUTES);
    renderPage("viewer");
    await ready();
    expect(screen.getByText("Evacuate the school")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add action/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("changes an action's status and reloads the list", async () => {
    const fetchFn = mockApi({ ...ROUTES, "PATCH /api/actions/12": [200, { ...ACTIONS[0], status: "in_progress" }] });
    renderPage("analyst");
    await ready();
    await userEvent.setup().click(item(12).getByRole("button", { name: "Start" }));

    await vi.waitFor(() => expect(callsTo(fetchFn, LIST)).toHaveLength(2));
    expect(body(fetchFn, "PATCH /api/actions/12")).toEqual({ status: "in_progress" });
  });

  it("shows the server's message when a status change is refused", async () => {
    mockApi({ ...ROUTES, "PATCH /api/actions/12": [403, { detail: "This action needs the 'analyst' role or higher." }] });
    renderPage("analyst");
    await ready();
    await userEvent.setup().click(item(12).getByRole("button", { name: "Start" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs the 'analyst' role");
  });

  it("lets only an admin delete, after a confirmation", async () => {
    const fetchFn = mockApi({ ...ROUTES, "DELETE /api/actions/10": [204, null] });
    renderPage("admin");
    const user = userEvent.setup();
    await ready();

    await user.click(item(10).getByRole("button", { name: "Delete" }));
    expect(callsTo(fetchFn, "DELETE /api/actions/10")).toHaveLength(0);
    await user.click(item(10).getByRole("button", { name: "Delete permanently" }));
    await vi.waitFor(() => expect(callsTo(fetchFn, "DELETE /api/actions/10")).toHaveLength(1));
    await vi.waitFor(() => expect(callsTo(fetchFn, LIST)).toHaveLength(2));
  });

  it("does not offer deleting to an analyst", async () => {
    mockApi(ROUTES);
    renderPage("analyst");
    await ready();
    expect(item(10).queryByRole("button", { name: "Delete" })).toBeNull();
    expect(item(10).getByRole("button", { name: "Reopen" })).toBeInTheDocument();
  });

  it("says so when the event does not exist", async () => {
    const missing = Object.fromEntries(
      ["/api/events/99", "/api/analyses?event_id=99&limit=50", "/api/events/99/actions?limit=200", "/api/events/99/actions/geojson"].map(
        (path) => [`GET ${path}`, [404, { detail: "Event 99 not found" }]],
      ),
    );
    mockApi(missing);
    renderPage("analyst", "/events/99");
    expect(await screen.findByRole("alert")).toHaveTextContent("Event 99 was not found.");
  });

  it("rejects a malformed event number without asking the server", async () => {
    const fetchFn = mockApi({});
    renderPage("analyst", "/events/abc");
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a valid event number/i);
    expect(fetchFn).not.toHaveBeenCalled();
  });
});
