import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ANALYSES, STATS, mockApi } from "../testUtils.js";
import Dashboard from "./Dashboard.jsx";

const ROUTES = (stats) => ({ "GET /api/stats/dashboard": [200, stats], "GET /api/analyses?limit=10": [200, ANALYSES] });
const renderPage = () =>
  render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );

describe("dashboard: repeats, severity overview and event links", () => {
  it("says how many analyses repeat an image that was already analysed", async () => {
    mockApi(ROUTES({ ...STATS, repeat_analyses: 3, severity_counts: { low: 0, moderate: 1, high: 0, severe: 1, not_classified: 4 } }));
    renderPage();
    expect(await screen.findByText(/3 of the completed analyses repeat an image/)).toBeInTheDocument();
    expect(screen.getByText(/counted again in these totals/)).toBeInTheDocument();
  });

  it("uses the singular for one repeat, and says nothing when there are none", async () => {
    mockApi(ROUTES({ ...STATS, repeat_analyses: 1 }));
    const { unmount } = renderPage();
    expect(await screen.findByText(/1 of the completed analyses repeats an image/)).toBeInTheDocument();
    unmount();

    mockApi(ROUTES({ ...STATS, repeat_analyses: 0 }));
    renderPage();
    await screen.findByTestId("stat-water");
    expect(screen.queryByText(/repeat/)).toBeNull();
  });

  it("shows the severity overview when the server sends counts", async () => {
    mockApi(ROUTES({ ...STATS, severity_counts: { low: 0, moderate: 1, high: 0, severe: 1, not_classified: 4 } }));
    renderPage();
    const box = await screen.findByTestId("severity-summary");
    expect(box).toHaveTextContent("Severe 1");
    expect(box).toHaveTextContent("Not classified yet: 4");
  });

  it("still works with an older server that sends neither field", async () => {
    mockApi(ROUTES(STATS));
    renderPage();
    await screen.findByTestId("stat-water");
    expect(screen.queryByTestId("severity-summary")).toBeNull();
    expect(screen.queryByText(/repeat/)).toBeNull();
  });

  it("links each event number to its event page", async () => {
    mockApi(ROUTES(STATS));
    renderPage();
    const table = await screen.findByRole("table");
    const links = within(table).getAllByRole("link", { name: "2" }).filter((a) => a.getAttribute("href") === "/events/2");
    expect(links.length).toBeGreaterThan(0);
  });
});
