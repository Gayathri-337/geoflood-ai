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

const COVERAGE = "GET /api/analyses/2/reference-coverage";

function renderPage() {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role: "analyst" }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/analyses/2"]}>
        <Routes>
          <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("analysis page: reference coverage", () => {
  it("explains in the Impact card that 0 can mean 'no data'", async () => {
    mockApi({
      ...ROUTES,
      [COVERAGE]: [200, { level: "none", counts: {}, empty_layers: [], message: "An impact of 0 here means there is no data for this area." }],
    });
    renderPage();
    await screen.findByTestId("map-stub");
    expect(await screen.findByRole("note")).toHaveTextContent(/no data for this area/);
  });

  it("still shows the page when the coverage cannot be loaded", async () => {
    mockApi({ ...ROUTES, [COVERAGE]: [500, { detail: "boom" }] });
    renderPage();
    await screen.findByTestId("map-stub");
    expect(screen.getByRole("heading", { name: /^impact$/i })).toBeInTheDocument();
    expect(screen.queryByRole("note")).toBeNull();
  });
});
