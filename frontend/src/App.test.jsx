import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "./App.jsx";
import { tokenStore } from "./api/client.js";
import { AuthProvider } from "./auth/AuthProvider.jsx";
import { ANALYSES, STATS, USER, callsTo, mockApi } from "./testUtils.js";

const DASHBOARD_ROUTES = {
  "GET /api/auth/me": [200, USER],
  "GET /api/stats/dashboard": [200, STATS],
  "GET /api/analyses?limit=10": [200, ANALYSES],
};
const LOGIN_OK = [200, { access_token: "tok-123", token_type: "bearer", expires_in: 28800 }];

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function signIn(user, name = "admin", password = "secret-pass-1") {
  await user.type(screen.getByLabelText(/username/i), name);
  await user.type(screen.getByLabelText(/password/i), password);
  await user.click(screen.getByRole("button", { name: /sign in/i }));
}

const signInHeading = () => screen.findByRole("heading", { name: /sign in/i });

describe("login and dashboard", () => {
  it("sends an anonymous visitor to the login page without asking for any data", async () => {
    const fetchFn = mockApi({});
    renderApp("/");
    await signInHeading();
    expect(callsTo(fetchFn, "GET /api/stats/dashboard")).toHaveLength(0);
  });

  it("shows the server's message for a wrong password", async () => {
    mockApi({ "POST /api/auth/login": [401, { detail: "Incorrect username or password." }] });
    renderApp("/login");
    await signIn(userEvent.setup());

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect username or password.");
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });

  it("logs in, stores the token and shows the dashboard", async () => {
    const fetchFn = mockApi({ "POST /api/auth/login": LOGIN_OK, ...DASHBOARD_ROUTES });
    renderApp("/");
    await signInHeading();
    await signIn(userEvent.setup());

    expect(await screen.findByTestId("stat-water")).toHaveTextContent("10.74");
    expect(screen.getByTestId("stat-new")).toHaveTextContent("3.87");
    expect(screen.getByText("Test Admin")).toBeInTheDocument();
    expect(tokenStore.get()).toBe("tok-123");

    const [, options] = callsTo(fetchFn, "GET /api/stats/dashboard")[0];
    expect(options.headers.Authorization).toBe("Bearer tok-123");
  });

  it("restores a saved session when the page is reloaded", async () => {
    tokenStore.set("saved-token");
    const fetchFn = mockApi(DASHBOARD_ROUTES);
    renderApp("/");

    expect(await screen.findByTestId("stat-water")).toHaveTextContent("10.74");
    const [, options] = callsTo(fetchFn, "GET /api/auth/me")[0];
    expect(options.headers.Authorization).toBe("Bearer saved-token");
  });

  it("drops a saved session whose token has expired", async () => {
    tokenStore.set("old-token");
    mockApi({ "GET /api/auth/me": [401, { detail: "Your session is invalid or has expired. Please log in again." }] });
    renderApp("/");

    await signInHeading();
    expect(tokenStore.get()).toBeNull();
  });

  it("logs out and forgets the token", async () => {
    tokenStore.set("saved-token");
    mockApi(DASHBOARD_ROUTES);
    renderApp("/");
    await screen.findByTestId("stat-water");

    await userEvent.setup().click(screen.getByRole("button", { name: /log out/i }));
    await signInHeading();
    expect(tokenStore.get()).toBeNull();
  });

  it("shows an error when the server fails, and recovers with 'Try again'", async () => {
    tokenStore.set("saved-token");
    let statsCalls = 0;
    mockApi({
      ...DASHBOARD_ROUTES,
      "GET /api/stats/dashboard": () =>
        ++statsCalls === 1 ? [503, { detail: "The database is unavailable or returned an error." }] : [200, STATS],
    });
    renderApp("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("The database is unavailable");
    await userEvent.setup().click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("stat-water")).toHaveTextContent("10.74");
  });

  it("lists recent analyses and marks analyses without a baseline", async () => {
    tokenStore.set("saved-token");
    mockApi(DASHBOARD_ROUTES);
    renderApp("/");

    const table = await screen.findByRole("table");
    expect(within(table).getByText("India_828067_S1Hand.tif")).toBeInTheDocument();
    expect(within(table).getByText("India_591317_S1Hand.tif")).toBeInTheDocument();
    expect(within(table).getByText("0.49")).toBeInTheDocument();
    expect(within(table).getByText("no baseline")).toBeInTheDocument();
  });

  it("shows a dash instead of a misleading 0.00 when no analysis had a baseline", async () => {
    tokenStore.set("saved-token");
    mockApi({
      ...DASHBOARD_ROUTES,
      "GET /api/stats/dashboard": [200, { ...STATS, analyses_with_baseline: 0, total_new_flood_area_km2: 0 }],
    });
    renderApp("/");

    expect(await screen.findByTestId("stat-new")).toHaveTextContent("–");
    expect(screen.getByTestId("stat-permanent")).toHaveTextContent("–");
    expect(screen.getByTestId("stat-water")).toHaveTextContent("10.74");
  });
});
