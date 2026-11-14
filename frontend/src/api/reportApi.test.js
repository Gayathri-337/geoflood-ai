import { describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client.js";

describe("report endpoint", () => {
  it("asks for the PDF of the analysis and returns it as a file", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    const fetchFn = vi.fn(async () => ({ ok: true, status: 200, text: async () => "", blob: async () => blob }));
    vi.stubGlobal("fetch", fetchFn);

    expect(await api.downloadReport(2)).toBe(blob);
    expect(new URL(fetchFn.mock.calls[0][0]).pathname).toBe("/api/analyses/2/report.pdf");
  });

  it("does not let an odd id change the address", async () => {
    const fetchFn = vi.fn(async () => ({ ok: true, status: 200, text: async () => "", blob: async () => new Blob([]) }));
    vi.stubGlobal("fetch", fetchFn);

    await api.downloadReport("2/../../users");
    expect(new URL(fetchFn.mock.calls[0][0]).pathname).toBe("/api/analyses/2%2F..%2F..%2Fusers/report.pdf");
  });

  it("turns an error answer into a readable ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 403, text: async () => JSON.stringify({ detail: "No." }), blob: async () => new Blob([]) })),
    );

    const failure = await api.downloadReport(2).catch((err) => err);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.status).toBe(403);
    expect(failure.message).toBe("No.");
  });
});
