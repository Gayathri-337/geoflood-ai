import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { ANALYSIS, FARMLAND, INFRASTRUCTURE, ROADS, SUMMARY, VILLAGES, ZONES } from "../mapFixtures.js";
import { SEVERITY } from "../severityFixtures.js";
import { USER, callsTo, mockApi } from "../testUtils.js";
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
const RUN = { analysis_id: 2, zone_type: "new_flood", compared_against: "x", near_m: 500, villages: 1, roads: 1, bridges: 0, farmland: 0, infrastructure: 1 };

function renderPage(role = "analyst") {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/analyses/2"]}>
        <Routes>
          <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("analysis page: severity", () => {
  it("shows the severity card, and the saved level appears in the page header", async () => {
    mockApi({ ...ROUTES, "POST /api/analyses/2/severity": [200, { ...SEVERITY, stored_severity: "high" }] });
    renderPage();
    expect(await screen.findByTestId("severity-level")).toHaveTextContent("High");
    expect(screen.getByText(/severity: not classified yet/i)).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: /save classification/i }));
    expect(await screen.findByText(/severity: high/i)).toBeInTheDocument();
  });

  it("works out the severity again after the impact is recomputed", async () => {
    const fetchFn = mockApi({ ...ROUTES, "POST /api/analyses/2/impact?near_m=500": [200, RUN] });
    renderPage();
    await screen.findByTestId("severity-level");
    expect(callsTo(fetchFn, `${BASE}/severity`)).toHaveLength(1);

    await userEvent.setup().click(screen.getByRole("button", { name: /compute impact/i }));
    await vi.waitFor(() => expect(callsTo(fetchFn, `${BASE}/severity`)).toHaveLength(2));
  });
});
