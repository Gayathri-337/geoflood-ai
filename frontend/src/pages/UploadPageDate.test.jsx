import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthContext } from "../auth/authContext.js";
import { USER, mockApi } from "../testUtils.js";
import UploadPage from "./UploadPage.jsx";

const LISTS = {
  "GET /api/events?limit=100": [200, [{ event_id: 2, name: "Assam flood demo", region_name: null, country: "India", status: "active" }]],
  "GET /api/sources": [200, [{ source_id: 1, name: "Sen1Floods11 hand-labeled chips", platform: "Sentinel-1" }]],
};
const tif = (name) => new File([new Uint8Array(16)], name, { type: "image/tiff" });
const posts = (fetchFn) => fetchFn.mock.calls.filter(([, options]) => options?.method === "POST");

function renderPage() {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role: "analyst" }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/upload"]}>
        <Routes>
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/analyses/:analysisId" element={<div>analysis page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}
const dateInput = () => screen.getByLabelText(/date the satellite took the image/i);

describe("upload page: observation date", () => {
  it("offers an optional date field that cannot be set in the future", async () => {
    mockApi(LISTS);
    renderPage();
    await screen.findByLabelText(/^event$/i);
    expect(dateInput()).toHaveAttribute("type", "date");
    expect(dateInput()).not.toBeRequired();
    expect(dateInput()).toHaveAttribute("max");
    expect(screen.getByText(/compare images of the same area over time/i)).toBeInTheDocument();
  });

  it("sends the date with the upload", async () => {
    const fetchFn = mockApi({ ...LISTS, "POST /api/analyses": [201, { analysis_id: 9 }] });
    renderPage();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText(/sentinel-1 image/i), tif("scene.tif"));
    fireEvent.change(dateInput(), { target: { value: "2026-10-27" } });
    await user.click(screen.getByRole("button", { name: /upload and analyse/i }));
    expect(await screen.findByText("analysis page")).toBeInTheDocument();
    expect(posts(fetchFn)[0][1].body.get("acquired_at")).toBe("2026-10-27");
  });

  it("sends no date when the field is left empty", async () => {
    const fetchFn = mockApi({ ...LISTS, "POST /api/analyses": [201, { analysis_id: 9 }] });
    renderPage();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText(/sentinel-1 image/i), tif("scene.tif"));
    await user.click(screen.getByRole("button", { name: /upload and analyse/i }));
    expect(await screen.findByText("analysis page")).toBeInTheDocument();
    expect(posts(fetchFn)[0][1].body.has("acquired_at")).toBe(false);
  });

  it("refuses a future date before anything is sent", async () => {
    const fetchFn = mockApi(LISTS);
    renderPage();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText(/sentinel-1 image/i), tif("scene.tif"));
    fireEvent.change(dateInput(), { target: { value: "2999-01-01" } });
    await user.click(screen.getByRole("button", { name: /upload and analyse/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot be in the future/);
    expect(posts(fetchFn)).toHaveLength(0);
  });
});
