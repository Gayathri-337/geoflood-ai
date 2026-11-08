import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { tokenStore } from "../api/client.js";
import { AuthContext } from "../auth/authContext.js";
import { USER, callsTo, fakeResponse, mockApi } from "../testUtils.js";
import UploadPage from "./UploadPage.jsx";

const EVENTS = [
  { event_id: 2, name: "Assam flood demo", region_name: null, country: "India", status: "active" },
  { event_id: 1, name: "Older event", region_name: null, country: null, status: "monitoring" },
];
const SOURCES = [
  { source_id: 1, name: "Sen1Floods11 hand-labeled chips", platform: "Sentinel-1" },
  { source_id: 2, name: "Sentinel-1 (Copernicus Data Space)", platform: "Sentinel-1" },
];
const LISTS = { "GET /api/events?limit=100": [200, EVENTS], "GET /api/sources": [200, SOURCES] };

const tif = (name, bytes = 16) => new File([new Uint8Array(bytes)], name, { type: "image/tiff" });
const posts = (fetchFn) => fetchFn.mock.calls.filter(([, options]) => options?.method === "POST");

function AnalysisStub() {
  const { analysisId } = useParams();
  return <div>analysis page {analysisId}</div>;
}

function renderPage(role = "analyst") {
  return render(
    <AuthContext.Provider value={{ user: { ...USER, role }, loading: false, login: vi.fn(), logout: vi.fn() }}>
      <MemoryRouter initialEntries={["/upload"]}>
        <Routes>
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/analyses/:analysisId" element={<AnalysisStub />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

const imageInput = () => screen.findByLabelText(/sentinel-1 image/i);
const baselineInput = () => screen.getByLabelText(/baseline water layer/i);
const submitButton = () => screen.getByRole("button", { name: /upload and analyse/i });

describe("upload page", () => {
  it("lists the events and sources, selecting the newest event and the first source", async () => {
    mockApi(LISTS);
    renderPage();
    const event = await screen.findByLabelText(/^event$/i);
    expect(event).toHaveValue("2");
    expect(within(event).getAllByRole("option").map((o) => o.textContent)).toEqual(["Assam flood demo", "Older event"]);
    expect(screen.getByLabelText(/imagery source/i)).toHaveValue("1");
  });

  it("tells a viewer that analysing needs the analyst role, without calling the server", async () => {
    const fetchFn = mockApi(LISTS);
    renderPage("viewer");
    expect(await screen.findByRole("alert")).toHaveTextContent(/needs the analyst role/i);
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it("asks for an image before uploading anything", async () => {
    const fetchFn = mockApi(LISTS);
    renderPage();
    await imageInput();
    await userEvent.setup().click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/Choose the Sentinel-1 image/);
    expect(posts(fetchFn)).toHaveLength(0);
  });

  it("refuses a file that is not a GeoTIFF", async () => {
    const fetchFn = mockApi(LISTS);
    renderPage();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(await imageInput(), tif("notes.txt"));
    await user.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/must be a GeoTIFF/);
    expect(posts(fetchFn)).toHaveLength(0);
  });

  it("refuses an image over the size limit", async () => {
    const fetchFn = mockApi(LISTS);
    renderPage();
    const big = tif("big.tif");
    Object.defineProperty(big, "size", { value: 201 * 1024 * 1024 });
    const user = userEvent.setup();
    await user.upload(await imageInput(), big);
    await user.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/larger than the 200 MB limit/);
    expect(posts(fetchFn)).toHaveLength(0);
  });

  it("uploads the files with the chosen event and source, then opens the new analysis", async () => {
    tokenStore.set("tok");
    const fetchFn = mockApi({ ...LISTS, "POST /api/analyses": [201, { analysis_id: 7 }] });
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("India_828067_S1Hand.tif"));
    await user.upload(baselineInput(), tif("India_828067_JRCWaterHand.tif"));
    await user.click(submitButton());

    expect(await screen.findByText("analysis page 7")).toBeInTheDocument();
    expect(posts(fetchFn)).toHaveLength(1);
    const [, options] = posts(fetchFn)[0];
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get("event_id")).toBe("2");
    expect(options.body.get("source_id")).toBe("1");
    expect(options.body.get("file").name).toBe("India_828067_S1Hand.tif");
    expect(options.body.get("baseline_file").name).toBe("India_828067_JRCWaterHand.tif");
    expect(options.headers.Authorization).toBe("Bearer tok");
    expect(options.headers["Content-Type"]).toBeUndefined();
  });

  it("sends no baseline when none was chosen", async () => {
    const fetchFn = mockApi({ ...LISTS, "POST /api/analyses": [201, { analysis_id: 8 }] });
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("scene.tif"));
    await user.click(submitButton());
    expect(await screen.findByText("analysis page 8")).toBeInTheDocument();
    expect(posts(fetchFn)[0][1].body.has("baseline_file")).toBe(false);
  });

  it("shows the server's message when the image is refused, and lets the user try again", async () => {
    const fetchFn = mockApi({
      ...LISTS,
      "POST /api/analyses": [422, { detail: "The image has 3 band(s); the model needs 2 (Sentinel-1 VV and VH in dB)." }],
    });
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("three_bands.tif"));
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("The image has 3 band(s)");
    expect(submitButton()).toBeEnabled();
    expect(screen.queryByText(/analysis page/)).toBeNull();
    await user.click(submitButton());
    await vi.waitFor(() => expect(posts(fetchFn)).toHaveLength(2));
  });

  it("explains when the server cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url, options = {}) =>
        options.method === "POST"
          ? Promise.reject(new TypeError("Failed to fetch"))
          : Promise.resolve(fakeResponse(200, new URL(url).pathname === "/api/sources" ? SOURCES : EVENTS)),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("a.tif"));
    await user.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });

  it("shows progress while the server works and sends the upload only once", async () => {
    let finish;
    const fetchFn = vi.fn((url, options = {}) => {
      if (options.method === "POST") {
        return new Promise((resolve) => {
          finish = () => resolve(fakeResponse(201, { analysis_id: 9 }));
        });
      }
      return Promise.resolve(fakeResponse(200, new URL(url).pathname === "/api/sources" ? SOURCES : EVENTS));
    });
    vi.stubGlobal("fetch", fetchFn);
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("a.tif"));
    await user.click(submitButton());

    const busy = await screen.findByRole("button", { name: /uploading and analysing/i });
    expect(busy).toBeDisabled();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    await user.click(busy);
    expect(posts(fetchFn)).toHaveLength(1);

    finish();
    expect(await screen.findByText("analysis page 9")).toBeInTheDocument();
  });

  it("warns when the image and the baseline look like different chips", async () => {
    mockApi(LISTS);
    renderPage();
    const user = userEvent.setup();
    await user.upload(await imageInput(), tif("India_828067_S1Hand.tif"));
    await user.upload(baselineInput(), tif("India_591317_JRCWaterHand.tif"));
    expect(screen.getByRole("status")).toHaveTextContent(/look like different chips/i);

    await user.upload(baselineInput(), tif("India_828067_JRCWaterHand.tif"));
    expect(screen.queryByText(/look like different chips/i)).toBeNull();
  });

  it("creates an event on the page and selects it", async () => {
    const fetchFn = mockApi({
      ...LISTS,
      "POST /api/events": [201, { event_id: 5, name: "New flood", region_name: null, country: "India", status: "monitoring" }],
    });
    renderPage();
    const user = userEvent.setup();
    await imageInput();
    await user.click(screen.getByRole("button", { name: /create a new event/i }));
    await user.type(screen.getByLabelText(/event name/i), "  New flood ");
    await user.type(screen.getByLabelText(/country/i), "India");
    await user.click(screen.getByRole("button", { name: /^create event$/i }));

    await vi.waitFor(() => expect(screen.getByLabelText(/^event$/i)).toHaveValue("5"));
    expect(JSON.parse(posts(fetchFn)[0][1].body)).toEqual({ name: "New flood", region_name: null, country: "India" });
    expect(within(screen.getByLabelText(/^event$/i)).getAllByRole("option")[0]).toHaveTextContent("New flood");
    expect(screen.queryByLabelText(/event name/i)).toBeNull();
  });

  it("needs an event name, and shows the server's message when an event is refused", async () => {
    const fetchFn = mockApi({ ...LISTS, "POST /api/events": [422, { detail: "Event name is not valid." }] });
    renderPage();
    const user = userEvent.setup();
    await imageInput();
    await user.click(screen.getByRole("button", { name: /create a new event/i }));

    await user.click(screen.getByRole("button", { name: /^create event$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Give the event a name.");
    expect(callsTo(fetchFn, "POST /api/events")).toHaveLength(0);

    await user.type(screen.getByLabelText(/event name/i), "x");
    await user.click(screen.getByRole("button", { name: /^create event$/i }));
    expect(await screen.findByText("Event name is not valid.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^event$/i)).toHaveValue("2"); // the selection did not change
  });
});
