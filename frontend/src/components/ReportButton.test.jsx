import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { tokenStore } from "../api/client.js";
import ReportButton from "./ReportButton.jsx";

const realCreate = URL.createObjectURL;
const realRevoke = URL.revokeObjectURL;
let clicked;

function pdfAnswer() {
  return {
    ok: true,
    status: 200,
    text: async () => "",
    blob: async () => new Blob(["%PDF-1.4 fake"], { type: "application/pdf" }),
  };
}
function errorAnswer(status, body) {
  return { ok: false, status, text: async () => JSON.stringify(body), blob: async () => new Blob([]) };
}

beforeEach(() => {
  clicked = [];
  URL.createObjectURL = vi.fn(() => "blob:fake-report");
  URL.revokeObjectURL = vi.fn();
  // jsdom cannot follow a download link: record the click instead
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function () {
    clicked.push({ href: this.href, download: this.download });
  });
});

afterEach(() => {
  URL.createObjectURL = realCreate;
  URL.revokeObjectURL = realRevoke;
});

describe("report button", () => {
  it("asks for the PDF with the login token and saves it under the analysis's name", async () => {
    tokenStore.set("test-token");
    const fetchFn = vi.fn(async () => pdfAnswer());
    vi.stubGlobal("fetch", fetchFn);
    render(<ReportButton analysisId={4} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /download report/i }));

    await vi.waitFor(() => expect(clicked).toHaveLength(1));
    const [url, options] = fetchFn.mock.calls[0];
    expect(new URL(url).pathname).toBe("/api/analyses/4/report.pdf");
    expect(options.method).toBe("GET");
    expect(options.headers.Authorization).toBe("Bearer test-token");
    expect(clicked[0]).toEqual({ href: "blob:fake-report", download: "geoflood_analysis_4_report.pdf" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is disabled while the report is being made, so one click makes one report", async () => {
    let finish;
    const fetchFn = vi.fn(() => new Promise((resolve) => (finish = () => resolve(pdfAnswer()))));
    vi.stubGlobal("fetch", fetchFn);
    render(<ReportButton analysisId={4} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /download report/i }));
    const busy = await screen.findByRole("button", { name: /preparing the report/i });
    expect(busy).toBeDisabled();
    finish();
    expect(await screen.findByRole("button", { name: /download report/i })).toBeEnabled();
    expect(fetchFn).toHaveBeenCalledTimes(1);
  });

  it("shows the server's message and offers the button again when the report fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => errorAnswer(404, { detail: "Analysis 4 not found" })));
    render(<ReportButton analysisId={4} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /download report/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Analysis 4 not found");
    expect(clicked).toHaveLength(0);
    expect(screen.getByRole("button", { name: /download report/i })).toBeEnabled();
  });

  it("says so when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("failed"))));
    render(<ReportButton analysisId={4} />);

    await userEvent.setup().click(screen.getByRole("button", { name: /download report/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });
});
