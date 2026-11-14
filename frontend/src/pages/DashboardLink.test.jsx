import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import Dashboard from "./Dashboard";
import { api } from "../api/client";

vi.mock("../api/client", () => ({
  api: {
    dashboard: vi.fn(),
    analyses: vi.fn(),
  },
}));

describe("dashboard links", () => {
  it("links every analysis to its map page", async () => {
    api.dashboard.mockResolvedValue({
      events: 2,
      images: 2,
      zone_polygons: 99,
      analyses_completed: 2,
      total_water_area_km2: 10.74,
      total_permanent_water_area_km2: 6.87,
      total_new_flood_area_km2: 3.87,
      analyses_with_baseline: 1,
      repeat_analyses: 0,
      latest_analysis_at: null,
      note: "Dashboard totals",
      severity_counts: {
        severe: 1,
        high: 0,
        moderate: 0,
        low: 1,
        not_classified: 0,
      },
    });

    api.analyses.mockResolvedValue([
      {
        analysis_id: 2,
        original_filename: "India_828067_S1Hand.tif",
        event_id: 2,
        water_area_km2: 0.54,
        baseline_method: "jrc",
        new_flood_area_km2: 0.49,
        zone_count: 40,
        severity: "severe",
        created_at: null,
      },
      {
        analysis_id: 1,
        original_filename: "India_591317_S1Hand.tif",
        event_id: 2,
        water_area_km2: 10.74,
        baseline_method: "none",
        new_flood_area_km2: null,
        zone_count: 47,
        severity: "low",
        created_at: null,
      },
    ]);

    const { container } = render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    );

    expect(
      await screen.findByText("India_828067_S1Hand.tif")
    ).toBeInTheDocument();

    expect(
      container.querySelector('a[href="/analyses/2"]')
    ).toBeInTheDocument();

    expect(
      container.querySelector('a[href="/analyses/1"]')
    ).toBeInTheDocument();
  });
});
