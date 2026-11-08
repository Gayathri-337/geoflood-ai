import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import {
  ANALYSIS, FARMLAND, INFRASTRUCTURE, ROADS, SUMMARY, SUMMARY_AFTER, VILLAGES, VILLAGES_AFTER, ZONES,
} from "../mapFixtures.js";
import { USER, callsTo, mockApi } from "../testUtils.js";
import AnalysisPage from "./AnalysisPage.jsx";

vi.mock("../map/AnalysisMap.jsx", async () => {
  const React = await import("react");
  return {
    default: ({ bounds, layers, visible, version }) =>
      React.createElement("div", {
        "data-testid": "map-stub",
        "data-bounds": JSON.stringify(bounds),
        "data-version": String(version),
        "data-visible": Object.keys(visible).filter((k) => visible[k]).sort().join(","),
        "data-counts": Object.keys(layers).sort().map((k) => `${k}:${layers[k]?.features?.length ?? 0}`).join(","),
      }),
  };
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
};
const RUN = { analysis_id: 2, zone_type: "new_flood", compared_against: "x", near_m: 500, villages: 2, roads: 1, bridges: 1, farmland: 0, infrastructure: 1 };

function renderPage(path = "/analyses/2", role = "analyst") {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/analyses/:analysisId" element={<AnalysisPage />} />
          <Route path="/" element={<div>dashboard</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const stub = () => screen.findByTestId("map-stub");

describe("analysis page", () => {
  it("loads the analysis, its zones and the four impact layers, and shows the figures", async () => {
    const fetchFn = mockApi(ROUTES);
    renderPage();

    expect(await screen.findByRole("heading", { name: /Analysis 2: India_828067_S1Hand\.tif/ })).toBeInTheDocument();
    expect(screen.getByTestId("fig-water")).toHaveTextContent("0.54");
    expect(screen.getByTestId("fig-permanent")).toHaveTextContent("0.05");
    expect(screen.getByTestId("fig-new")).toHaveTextContent("0.49");
    for (const key of Object.keys(ROUTES)) expect(callsTo(fetchFn, key)).toHaveLength(1);

    const map = await stub();
    expect(JSON.parse(map.dataset.bounds)).toEqual(ANALYSIS.bounds_wgs84);
    expect(map.dataset.counts).toBe("farmland:0,infrastructure:1,roads:2,villages:1,zones:2");
    expect(map.dataset.visible).toBe("farmland,infrastructure,roads,villages,zones");
  });

  it("shows counts next to each layer", async () => {
    mockApi(ROUTES);
    renderPage();
    await stub();
    expect(screen.getByRole("checkbox", { name: /Affected roads/ })).toHaveAccessibleName(
      /1 \(120 m flooded\), plus 1 bridge over water/,
    );
    expect(screen.getByRole("checkbox", { name: /Affected villages/ })).toHaveAccessibleName(/1 \(0 inside, 1 near\)/);
    expect(screen.getByRole("checkbox", { name: /Affected farmland/ })).toHaveAccessibleName(/0 \(0\.000 km² flooded\)/);
    expect(screen.getByRole("checkbox", { name: /Detected water zones/ })).toHaveAccessibleName(/2 polygons/);
    expect(screen.getByText("Permanent water (on the baseline)")).toBeInTheDocument();
    expect(screen.getAllByText("New water vs baseline")).toHaveLength(2); // the figures list and the legend
  });

  it("explains bridges in the legend", async () => {
    mockApi(ROUTES);
    renderPage();
    await stub();
    expect(screen.getByText("Bridge over the water (not counted as flooded)")).toBeInTheDocument();
  });

  it("shows no bridge legend when there are no bridges", async () => {
    mockApi({
      ...ROUTES,
      [`${BASE}/impact`]: [200, { ...SUMMARY, roads: { count: 1, flooded_length_km: 0.12, bridges: { count: 0, length_km: 0 } } }],
    });
    renderPage();
    await stub();
    expect(screen.queryByText(/Bridge over the water/)).toBeNull();
    expect(screen.getByRole("checkbox", { name: /Affected roads/ })).not.toHaveAccessibleName(/bridge/i);
  });

  it("switches a layer off and on with its checkbox", async () => {
    mockApi(ROUTES);
    renderPage();
    const user = userEvent.setup();
    await stub();

    await user.click(screen.getByRole("checkbox", { name: /Affected roads/ }));
    expect((await stub()).dataset.visible).toBe("farmland,infrastructure,villages,zones");
    await user.click(screen.getByRole("checkbox", { name: /Affected roads/ }));
    expect((await stub()).dataset.visible).toBe("farmland,infrastructure,roads,villages,zones");
  });

  it("does not offer 'Compute impact' to a viewer", async () => {
    mockApi(ROUTES);
    renderPage("/analyses/2", "viewer");
    await stub();
    expect(screen.queryByRole("button", { name: /compute impact/i })).toBeNull();
    expect(screen.getByText(/needs the analyst role/i)).toBeInTheDocument();
  });

  it("recomputes the impact with the default distance and refreshes the layers", async () => {
    let computed = false;
    const fetchFn = mockApi({
      ...ROUTES,
      [`${BASE}/impact`]: () => [200, computed ? SUMMARY_AFTER : SUMMARY],
      [`${BASE}/impact/villages`]: () => [200, computed ? VILLAGES_AFTER : VILLAGES],
      "POST /api/analyses/2/impact?near_m=500": () => {
        computed = true;
        return [200, RUN];
      },
    });
    renderPage();
    const user = userEvent.setup();
    await stub();

    await user.click(screen.getByRole("button", { name: /compute impact/i }));
    expect(await screen.findByRole("checkbox", { name: /2 \(1 inside, 1 near\)/ })).toBeInTheDocument();
    expect(callsTo(fetchFn, "POST /api/analyses/2/impact?near_m=500")).toHaveLength(1);
    const map = await stub();
    expect(map.dataset.version).toBe("2");
    expect(map.dataset.counts).toContain("villages:2");
  });

  it("sends the distance the user typed", async () => {
    const fetchFn = mockApi({ ...ROUTES, "POST /api/analyses/2/impact?near_m=300": [200, RUN] });
    renderPage();
    const user = userEvent.setup();
    await stub();

    const input = screen.getByLabelText(/near.*distance/i);
    await user.clear(input);
    await user.type(input, "300");
    await user.click(screen.getByRole("button", { name: /compute impact/i }));
    await vi.waitFor(() => expect(callsTo(fetchFn, "POST /api/analyses/2/impact?near_m=300")).toHaveLength(1));
  });

  it.each(["20000", "-5", ""])("refuses the distance '%s' without calling the server", async (bad) => {
    const fetchFn = mockApi(ROUTES);
    renderPage();
    const user = userEvent.setup();
    await stub();

    const input = screen.getByLabelText(/near.*distance/i);
    await user.clear(input);
    if (bad) await user.type(input, bad);
    await user.click(screen.getByRole("button", { name: /compute impact/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/between 0 and 10000/);
    expect(fetchFn.mock.calls.filter(([, options]) => options.method === "POST")).toHaveLength(0);
  });

  it("shows the server's message when computing is refused", async () => {
    mockApi({
      ...ROUTES,
      "POST /api/analyses/2/impact?near_m=500": [403, { detail: "This action needs the 'analyst' role or higher." }],
    });
    renderPage();
    await stub();
    await userEvent.setup().click(screen.getByRole("button", { name: /compute impact/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs the 'analyst' role");
  });

  it("says so when the analysis does not exist", async () => {
    const missing = Object.fromEntries(
      ["", "/zones", "/impact", "/impact/villages", "/impact/roads", "/impact/farmland", "/impact/infrastructure"].map((suffix) => [
        `GET /api/analyses/99${suffix}`,
        [404, { detail: "Analysis 99 not found" }],
      ]),
    );
    mockApi(missing);
    renderPage("/analyses/99");
    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis 99 was not found.");
  });

  it("rejects a malformed analysis number without asking the server", async () => {
    const fetchFn = mockApi({});
    renderPage("/analyses/abc");
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a valid analysis number/i);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("shows dashes for the baseline figures when no baseline was used", async () => {
    mockApi({
      ...ROUTES,
      [BASE]: [200, { ...ANALYSIS, baseline_method: "none", permanent_water_area_km2: null, new_flood_area_km2: null }],
      [`${BASE}/impact`]: [200, { ...SUMMARY, compared_against: "all detected water (no baseline layer was used)" }],
    });
    renderPage();
    await stub();
    expect(screen.getByTestId("fig-permanent")).toHaveTextContent("–");
    expect(screen.getByTestId("fig-new")).toHaveTextContent("–");
    expect(screen.getByTestId("fig-water")).toHaveTextContent("0.54");
    expect(screen.getByText(/permanent and new water are not separated/i)).toBeInTheDocument();
    expect(screen.getByText(/Detected water \(no baseline\)/)).toBeInTheDocument();
  });

  it("shows the warnings of an analysis", async () => {
    mockApi({ ...ROUTES, [BASE]: [200, { ...ANALYSIS, warnings: ["Band 1 median is 93.4, which does not look like dB."] }] });
    renderPage();
    await stub();
    expect(screen.getByRole("alert")).toHaveTextContent("does not look like dB");
  });

  it("shows a server error and recovers with 'Try again'", async () => {
    let failing = true;
    mockApi({ ...ROUTES, [BASE]: () => (failing ? [503, { detail: "The database is unavailable or returned an error." }] : [200, ANALYSIS]) });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("The database is unavailable");

    failing = false;
    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));
    expect(await stub()).toBeInTheDocument();
  });
});