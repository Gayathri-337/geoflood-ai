import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi } from "../testUtils.js";
import CoverageNote from "./CoverageNote.jsx";

const KEY = "GET /api/analyses/5/reference-coverage";
const body = (level, message) => ({ analysis_id: 5, level, message, counts: {}, empty_layers: [] });

describe("coverage note", () => {
  it("warns when there is no reference data in the image", async () => {
    mockApi({ [KEY]: [200, body("none", "No villages, roads, farmland or facilities lie inside this image.")] });
    render(<CoverageNote analysisId="5" />);
    const note = await screen.findByRole("note");
    expect(note).toHaveTextContent(/No villages, roads, farmland or facilities/);
    expect(note).toHaveClass("alert-warning");
  });

  it("warns when only some layers are empty", async () => {
    mockApi({ [KEY]: [200, body("partial", "The reference data has no farmland inside this image.")] });
    render(<CoverageNote analysisId="5" />);
    expect(await screen.findByRole("note")).toHaveTextContent(/no farmland inside this image/);
  });

  it("shows a quiet line when every layer has data", async () => {
    mockApi({ [KEY]: [200, body("ok", "Reference data inside this image: 1 village, 104 road segments.")] });
    render(<CoverageNote analysisId="5" />);
    expect(await screen.findByTestId("coverage-note")).toHaveTextContent(/1 village, 104 road segments/);
    expect(screen.queryByRole("note")).toBeNull();
  });

  it("shows nothing, and no alert, when the server cannot answer", async () => {
    const fetchFn = mockApi({ [KEY]: [500, { detail: "boom" }] });
    const { container } = render(<CoverageNote analysisId="5" />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(fetchFn).toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });
});
