import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { EMPTY_PROGRESSION, PROGRESSION } from "../progressionFixtures.js";
import { mockApi } from "../testUtils.js";
import ProgressionPanel from "./ProgressionPanel.jsx";

const KEY = "GET /api/events/2/progression";

function renderPanel() {
  return render(
    <MemoryRouter>
      <ProgressionPanel eventId="2" />
    </MemoryRouter>,
  );
}

describe("progression panel", () => {
  it("draws the chart and lists every date with its change", async () => {
    mockApi({ [KEY]: [200, PROGRESSION] });
    renderPanel();

    const chart = await screen.findByRole("img", { name: /detected water area in km²/i });
    expect(chart).toHaveAccessibleName(/2026-10-01 \(2\.50 km²\) to 2026-10-13 \(6\.80 km²\)/);
    expect(screen.getByRole("heading", { name: /change over time/i })).toBeInTheDocument();

    const rows = within(screen.getByTestId("series-1")).getAllByRole("row");
    expect(rows).toHaveLength(4); // header + 3 dates
    expect(rows[1]).toHaveTextContent("2026-10-01");
    expect(rows[1]).toHaveTextContent(/first date/);
    expect(rows[2]).toHaveTextContent("More detected water");
    expect(rows[2]).toHaveTextContent("+1.70 km² (+68.0%) in 6 days");
    expect(rows[3]).toHaveTextContent("+2.60 km² (+61.9%) in 6 days");
    expect(within(rows[3]).getByRole("link", { name: "Analysis 3" })).toHaveAttribute("href", "/analyses/3");
    expect(screen.getByText(/changed by \+4\.30 km² \(\+172\.0%\)/)).toBeInTheDocument();
  });

  it("explains the analyses that were not compared", async () => {
    mockApi({ [KEY]: [200, PROGRESSION] });
    renderPanel();
    expect(await screen.findByText(/1 analysis is not compared/)).toBeInTheDocument();
    expect(screen.getByText(/No observation date\./)).toBeInTheDocument();
    expect(screen.getByText(/cannot be placed in time/)).toBeInTheDocument();
    expect(screen.getByText("Analysis 5").closest("a")).toHaveAttribute("href", "/analyses/5");
  });

  it("states that a change is not proof of flooding, and never calls the result confirmed", async () => {
    mockApi({ [KEY]: [200, PROGRESSION] });
    const { container } = renderPanel();
    expect(await screen.findByText(/not proof that the flood grew or shrank/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/confirmed|real-time|live monitoring/i);
  });

  it("shows warnings of a series", async () => {
    const warned = structuredClone(PROGRESSION);
    warned.series[0].warnings = ["The images overlap by only 87% of their combined extent."];
    mockApi({ [KEY]: [200, warned] });
    renderPanel();
    expect(await screen.findByRole("note")).toHaveTextContent(/overlap by only 87%/);
  });

  it("says what to do when nothing can be compared yet", async () => {
    mockApi({ [KEY]: [200, EMPTY_PROGRESSION] });
    renderPanel();
    expect(await screen.findByText(/Nothing to compare yet/)).toBeInTheDocument();
    expect(screen.getByText(/enter the date the satellite took each image/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText(/not compared/)).toBeNull();
  });

  it("quietly says so when the comparison cannot be loaded, without an alert", async () => {
    mockApi({ [KEY]: [500, { detail: "boom" }] });
    renderPanel();
    expect(await screen.findByText(/could not be loaded just now/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not draw a chart for a series without enough water areas", async () => {
    const holes = structuredClone(PROGRESSION);
    holes.series[0].points.forEach((p, i) => {
      if (i > 0) p.water_area_km2 = null;
    });
    mockApi({ [KEY]: [200, holes] });
    renderPanel();
    expect(await screen.findByText(/Not enough water-area values to draw a chart/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
