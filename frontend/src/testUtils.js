import { vi } from "vitest";

export const USER = {
  user_id: 1,
  username: "admin",
  email: "admin@example.com",
  full_name: "Test Admin",
  role: "admin",
  is_active: true,
  created_at: "2026-11-01T14:15:51Z",
};

export const STATS = {
  events: 2,
  images: 2,
  analyses_completed: 2,
  analyses_with_baseline: 2,
  zone_polygons: 99,
  total_water_area_km2: 10.74337,
  total_permanent_water_area_km2: 6.874565,
  total_new_flood_area_km2: 3.868805,
  latest_analysis_at: "2026-11-03T17:06:12Z",
  note: "Totals add up separate analyses. If two analyses cover the same ground, that area is counted twice.",
};

export const ANALYSES = [
  {
    analysis_id: 2,
    event_id: 2,
    original_filename: "India_828067_S1Hand.tif",
    baseline_method: "jrc",
    water_area_km2: 0.54,
    new_flood_area_km2: 0.49,
    zone_count: 40,
    status: "completed",
    created_at: "2026-11-03T17:06:12Z",
  },
  {
    analysis_id: 1,
    event_id: 2,
    original_filename: "India_591317_S1Hand.tif",
    baseline_method: "none",
    water_area_km2: 10.74337,
    new_flood_area_km2: null,
    zone_count: 47,
    status: "completed",
    created_at: "2026-10-27T10:12:50Z",
  },
];

/** What the app needs from fetch(): status, ok and text(). */
export function fakeResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined || body === null ? "" : JSON.stringify(body)),
  };
}

/** Replace fetch with a function that answers every call with handler(url, options). */
export function mockFetch(handler) {
  const fetchFn = vi.fn((url, options = {}) => Promise.resolve(handler(new URL(url), options)));
  vi.stubGlobal("fetch", fetchFn);
  return fetchFn;
}

const keyOf = (url, options) => `${options.method || "GET"} ${url.pathname}${url.search}`;

/** A fake backend. routes: { "GET /api/auth/me": [200, body] } (or a function returning [status, body]). */
export function mockApi(routes) {
  return mockFetch((url, options) => {
    const key = keyOf(url, options);
    const route = routes[key];
    if (!route) return fakeResponse(500, { detail: `no mock for ${key}` });
    const [status, body] = typeof route === "function" ? route(options) : route;
    return fakeResponse(status, body);
  });
}

/** The calls a fetch mock received for one route key. */
export function callsTo(fetchFn, key) {
  return fetchFn.mock.calls.filter(([url, options = {}]) => keyOf(new URL(url), options) === key);
}
