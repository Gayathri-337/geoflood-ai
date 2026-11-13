import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { EVENT } from "../eventFixtures.js";
import { mockApi } from "../testUtils.js";
import EventsPage from "./EventsPage.jsx";

const OLDER = { ...EVENT, event_id: 1, name: "Older event", region_name: null, country: null, status: "resolved" };
const renderPage = () =>
  render(
    <MemoryRouter>
      <EventsPage />
    </MemoryRouter>,
  );

describe("events page", () => {
  it("lists the events, each linking to its page", async () => {
    mockApi({ "GET /api/events?limit=100": [200, [EVENT, OLDER]] });
    renderPage();
    expect(await screen.findByRole("link", { name: "Assam flood demo" })).toHaveAttribute("href", "/events/2");
    expect(screen.getByRole("link", { name: "Older event" })).toHaveAttribute("href", "/events/1");
    expect(screen.getByText("Brahmaputra valley, India")).toBeInTheDocument();
    expect(screen.getByText("resolved")).toBeInTheDocument();
  });

  it("says when there are no events", async () => {
    mockApi({ "GET /api/events?limit=100": [200, []] });
    renderPage();
    expect(await screen.findByText(/No events yet/)).toBeInTheDocument();
  });

  it("shows an error and recovers with 'Try again'", async () => {
    let failing = true;
    mockApi({ "GET /api/events?limit=100": () => (failing ? [503, { detail: "The database is unavailable or returned an error." }] : [200, [EVENT]]) });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("The database is unavailable");
    failing = false;
    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("link", { name: "Assam flood demo" })).toBeInTheDocument();
  });
});
