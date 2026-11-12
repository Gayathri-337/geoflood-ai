import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SEVERITY, SEVERITY_NO_IMPACT, SEVERITY_SKIPPED_STEP } from "../severityFixtures.js";
import { callsTo, mockApi } from "../testUtils.js";
import SeverityCard from "./SeverityCard.jsx";

const GET = "GET /api/analyses/2/severity";
const POST = "POST /api/analyses/2/severity";

describe("severity card", () => {
  it("shows the overall level, the reason and every indicator with its limits", async () => {
    mockApi({ [GET]: [200, SEVERITY] });
    render(<SeverityCard analysisId="2" canSave />);

    const badge = await screen.findByTestId("severity-level");
    expect(badge).toHaveTextContent("High");
    expect(badge.className).toContain("text-bg-danger");
    expect(screen.getByText(/Decided by:/)).toHaveTextContent("Facilities inside the flooded area");

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(6); // the header and five indicators
    expect(within(table).getByText("2.1%")).toBeInTheDocument();
    expect(within(table).getByText("0.00 km")).toBeInTheDocument();
    expect(within(table).getByText("0.000 km²")).toBeInTheDocument();
    expect(within(table).getByText("moderate from 2%, high from 10%, severe from 25%")).toBeInTheDocument();
    expect(within(table).getByText("moderate from 1, high from 2, severe from 3")).toBeInTheDocument();
    expect(screen.getByText(/not calibrated against damage data/)).toBeInTheDocument();
  });

  it("explains the critical-facility rule and says how many of the facilities are critical", async () => {
    mockApi({ [GET]: [200, SEVERITY] });
    render(<SeverityCard analysisId="2" canSave />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("1 critical")).toBeInTheDocument();
    expect(within(table).getByText(/inside counts as high on its own/)).toBeInTheDocument();
  });

  it("copes with a rule that has no 'moderate' step", async () => {
    mockApi({ [GET]: [200, SEVERITY_SKIPPED_STEP] });
    render(<SeverityCard analysisId="2" canSave />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("high from 1, severe from 3")).toBeInTheDocument();
    expect(within(table).queryByText("1 critical")).toBeNull(); // no detail was sent
  });

  it("says when the impact has not been computed", async () => {
    mockApi({ [GET]: [200, SEVERITY_NO_IMPACT] });
    render(<SeverityCard analysisId="2" canSave />);
    expect(await screen.findByText(/Impact has not been computed/)).toBeInTheDocument();
    expect(screen.getAllByText("not computed")).toHaveLength(4);
    expect(screen.getByTestId("severity-level")).toHaveTextContent("Moderate");
  });

  it("tells whether the level is saved, not saved, or out of date", async () => {
    mockApi({ [GET]: [200, SEVERITY] });
    const { unmount } = render(<SeverityCard analysisId="2" canSave />);
    expect(await screen.findByTestId("severity-stored")).toHaveTextContent("Not saved yet.");
    unmount();

    mockApi({ [GET]: [200, { ...SEVERITY, stored_severity: "high" }] });
    const second = render(<SeverityCard analysisId="2" canSave />);
    expect(await screen.findByTestId("severity-stored")).toHaveTextContent("Saved.");
    second.unmount();

    mockApi({ [GET]: [200, { ...SEVERITY, stored_severity: "moderate" }] });
    render(<SeverityCard analysisId="2" canSave />);
    expect(await screen.findByTestId("severity-stored")).toHaveTextContent(/saved severity \(Moderate\) is out of date/i);
  });

  it("saves the classification and reports it to the page", async () => {
    const fetchFn = mockApi({ [GET]: [200, SEVERITY], [POST]: [200, { ...SEVERITY, stored_severity: "high" }] });
    const onSaved = vi.fn();
    render(<SeverityCard analysisId="2" canSave onSaved={onSaved} />);

    await userEvent.setup().click(await screen.findByRole("button", { name: /save classification/i }));
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledWith("high");
    expect(callsTo(fetchFn, POST)).toHaveLength(1);
  });

  it("does not offer saving to someone who may not save", async () => {
    mockApi({ [GET]: [200, SEVERITY] });
    render(<SeverityCard analysisId="2" canSave={false} />);
    await screen.findByTestId("severity-level");
    expect(screen.queryByRole("button", { name: /save classification/i })).toBeNull();
    expect(screen.getByText(/Only analysts can save the classification/)).toBeInTheDocument();
  });

  it("shows a quiet message, not an alert, when the severity cannot be loaded", async () => {
    mockApi({ [GET]: [503, { detail: "The database is unavailable or returned an error." }] });
    render(<SeverityCard analysisId="2" canSave />);
    expect(await screen.findByText(/Severity is unavailable: The database is unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the server's message when saving is refused", async () => {
    mockApi({ [GET]: [200, SEVERITY], [POST]: [403, { detail: "This action needs the 'analyst' role or higher." }] });
    render(<SeverityCard analysisId="2" canSave />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /save classification/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("needs the 'analyst' role");
  });

  it("loads again when the page asks for a refresh", async () => {
    const fetchFn = mockApi({ [GET]: [200, SEVERITY] });
    const { rerender } = render(<SeverityCard analysisId="2" canSave refreshKey={0} />);
    await screen.findByTestId("severity-level");
    rerender(<SeverityCard analysisId="2" canSave refreshKey={1} />);
    await vi.waitFor(() => expect(callsTo(fetchFn, GET)).toHaveLength(2));
  });
});