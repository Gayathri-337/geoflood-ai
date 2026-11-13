import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { ANALYSIS, FARMLAND, INFRASTRUCTURE, ROADS, SUMMARY, VILLAGES, ZONES } from "../mapFixtures.js";
import { SEVERITY } from "../severityFixtures.js";
import { USER, mockApi } from "../testUtils.js";
import AnalysisPage from "./AnalysisPage.jsx";

vi.mock("../map/AnalysisMap.jsx", async () => {
  const React = await import("react");
  return { default: () => React.createElement("div", { "data-testid": "map-stub" }) };
});

const BASE = "GET /api/analyses/2";
const ROUTES = {
  [BASE]: [200, ANALYSIS],
  [`${BASE}/zones`]: [200, ZONES],
  [`${BASE}/impact`]: [200, SUMMARY],
  [`${BASE}/impact/villages`]: [200, VILLAGES],
  [`${BASE}/impact/roads`]: [200, ROADS],
  [`${BASE}/impact/farmland`]: [200, FARMLAND],
  [`${BASE}/impact/infrastructure`]: [200, INFRASTRUCTURE],
  [`${BASE}/severity`]: [200, SEVERITY],
};

describe("analysis page: event link", () => {
  it("links the event number to the event page", async () => {
    mockApi(ROUTES);
    render(
      <AuthContext.Provider value={{ user: USER, loading: false, login: vi.fn(), logout: vi.fn() }}>
        <MemoryRouter initialEntries={["/analyses/2"]}>
          <Routes>
            <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    await screen.findByTestId("map-stub");
    expect(screen.getByRole("link", { name: "Event 2" })).toHaveAttribute("href", "/events/2");
  });
});
