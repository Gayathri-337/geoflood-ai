import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ANALYSES, STATS, mockApi } from "../testUtils.js";
import Dashboard from "./Dashboard.jsx";

describe("dashboard links", () => {
  it("links every analysis to its map page", async () => {
    mockApi({ "GET /api/stats/dashboard": [200, STATS], "GET /api/analyses?limit=10": [200, ANALYSES] });
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "2" })).toHaveAttribute("href", "/analyses/2");
    expect(screen.getByRole("link", { name: "1" })).toHaveAttribute("href", "/analyses/1");
  });
});
