import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ANALYSES, STATS, mockApi } from "../testUtils.js";
import Dashboard from "./Dashboard.jsx";

describe("dashboard severity column", () => {
  it("shows the saved severity as a badge and a dash when there is none", async () => {
    mockApi({
      "GET /api/stats/dashboard": [200, STATS],
      "GET /api/analyses?limit=10": [200, [{ ...ANALYSES[0], severity: "high" }, { ...ANALYSES[1], severity: null }]],
    });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Severity" })).toBeInTheDocument();
    expect(within(table).getByText("High").className).toContain("text-bg-danger");
    expect(within(table).getAllByText("–")).toHaveLength(1);
  });
});
