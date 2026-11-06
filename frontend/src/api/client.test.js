import { describe, expect, it, vi, afterEach } from "vitest";
import { api, setUnauthorizedHandler, tokenStore } from "./client.js";
import { fakeResponse, mockFetch } from "../testUtils.js";

afterEach(() => setUnauthorizedHandler(null));

describe("api client", () => {
  it("logs in with a form body and without any Authorization header", async () => {
    tokenStore.set("an-old-token");
    const fetchFn = mockFetch(() => fakeResponse(200, { access_token: "t", token_type: "bearer", expires_in: 60 }));
    const result = await api.login("admin", "pw x");

    const [url, options] = fetchFn.mock.calls[0];
    expect(url.endsWith("/api/auth/login")).toBe(true);
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    expect(options.headers.Authorization).toBeUndefined();
    const form = new URLSearchParams(options.body);
    expect(form.get("username")).toBe("admin");
    expect(form.get("password")).toBe("pw x");
    expect(result.access_token).toBe("t");
  });

  it("sends the Bearer token once logged in", async () => {
    tokenStore.set("abc");
    const fetchFn = mockFetch(() => fakeResponse(200, { user_id: 1 }));
    await api.me();
    expect(fetchFn.mock.calls[0][1].headers.Authorization).toBe("Bearer abc");
  });

  it("sends no Authorization header when there is no token", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, []));
    await api.analyses(3);
    expect(fetchFn.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("reports a 401 on a logged-in request and tells the app the session ended", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    tokenStore.set("expired");
    mockFetch(() => fakeResponse(401, { detail: "Your session is invalid or has expired. Please log in again." }));

    await expect(api.me()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: expect.stringContaining("expired"),
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not treat a wrong password as an ended session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(() => fakeResponse(401, { detail: "Incorrect username or password." }));

    await expect(api.login("admin", "wrong")).rejects.toMatchObject({
      status: 401,
      message: "Incorrect username or password.",
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("joins validation messages and falls back to a generic message", async () => {
    mockFetch(() => fakeResponse(422, { detail: [{ msg: "Field required" }, { msg: "Value is not valid" }] }));
    await expect(api.dashboard()).rejects.toMatchObject({ status: 422, message: "Field required; Value is not valid" });

    mockFetch(() => fakeResponse(503));
    await expect(api.dashboard()).rejects.toMatchObject({
      status: 503,
      message: "The server answered with an error (503).",
    });
  });

  it("explains when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.dashboard()).rejects.toMatchObject({
      status: 0,
      message: "Cannot reach the server. Is the backend running?",
    });
  });

  it("calls the expected addresses", async () => {
    const fetchFn = mockFetch(() => fakeResponse(200, {}));
    await api.dashboard();
    await api.analyses(5);
    expect(fetchFn.mock.calls[0][0].endsWith("/api/stats/dashboard")).toBe(true);
    expect(fetchFn.mock.calls[1][0].endsWith("/api/analyses?limit=5")).toBe(true);
  });

  it("keeps the token in sessionStorage", () => {
    tokenStore.set("abc");
    expect(sessionStorage.getItem("geoflood.token")).toBe("abc");
    tokenStore.clear();
    expect(sessionStorage.getItem("geoflood.token")).toBeNull();
    expect(tokenStore.get()).toBeNull();
  });

  it("keeps working when the browser blocks storage", () => {
    const blocked = () => {
      throw new Error("blocked");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(blocked);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(blocked);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(blocked);

    expect(tokenStore.get()).toBeNull();
    tokenStore.set("kept-in-memory");
    expect(tokenStore.get()).toBe("kept-in-memory");
    tokenStore.clear();
    expect(tokenStore.get()).toBeNull();
  });
});
