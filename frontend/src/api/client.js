/**
 * GeoFlood AI frontend - the only place that talks to the backend.
 * Every request goes through request(): it adds the login token, turns error answers into an
 * ApiError with a readable message, and tells the app when the session is no longer valid (401).
 */

const BASE_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const TOKEN_KEY = "geoflood.token";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status; // 0 means the server could not be reached
  }
}

// The login token lives in sessionStorage: it survives a page reload but disappears when the tab
// is closed. A copy is kept in memory so that login still works if the browser blocks storage.
let memoryToken = null;

export const tokenStore = {
  get() {
    if (memoryToken) return memoryToken;
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    memoryToken = token;
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage blocked: the login lasts until the page is reloaded */
    }
  },
  clear() {
    memoryToken = null;
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* nothing to remove */
    }
  },
};

let unauthorizedHandler = null;

/** The app registers a function that is called whenever the server answers 401 to a logged-in request. */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

function messageFrom(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg || "Invalid value").join("; ");
  }
  return `The server answered with an error (${status}).`;
}

async function request(path, { method = "GET", body, form, formData, auth = true } = {}) {
  const headers = {};
  const token = auth ? tokenStore.get() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let payload;
  if (formData) {
    payload = formData; // the browser adds the multipart Content-Type (with its boundary) itself
  } else if (form) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    payload = new URLSearchParams(form).toString();
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method, headers, body: payload });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }

  let data = null;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (response.status === 401 && auth && unauthorizedHandler) unauthorizedHandler();
  if (!response.ok) throw new ApiError(messageFrom(data, response.status), response.status);
  return data;
}

export const api = {
  // auth: false, so that a wrong password does not count as "your session ended"
  login: (username, password) =>
    request("/api/auth/login", { method: "POST", form: { username, password }, auth: false }),
  me: () => request("/api/auth/me"),
  dashboard: () => request("/api/stats/dashboard"),
  analyses: (limit = 10) => request(`/api/analyses?limit=${encodeURIComponent(limit)}`),
  analysis: (id) => request(`/api/analyses/${encodeURIComponent(id)}`),
  zones: (id) => request(`/api/analyses/${encodeURIComponent(id)}/zones`),
  impactSummary: (id) => request(`/api/analyses/${encodeURIComponent(id)}/impact`),
  impactLayer: (id, layer) =>
    request(`/api/analyses/${encodeURIComponent(id)}/impact/${encodeURIComponent(layer)}`),
  computeImpact: (id, nearM) =>
    request(`/api/analyses/${encodeURIComponent(id)}/impact?near_m=${encodeURIComponent(nearM)}`, {
      method: "POST",
    }),
  events: (limit = 100) => request(`/api/events?limit=${encodeURIComponent(limit)}`),
  sources: () => request("/api/sources"),
  createEvent: (event) => request("/api/events", { method: "POST", body: event }),
  createAnalysis: ({ file, baselineFile, eventId, sourceId }) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("event_id", String(eventId));
    formData.append("source_id", String(sourceId));
    if (baselineFile) formData.append("baseline_file", baselineFile);
    return request("/api/analyses", { method: "POST", formData });
  },
  severity: (id) => request(`/api/analyses/${encodeURIComponent(id)}/severity`),
  saveSeverity: (id) => request(`/api/analyses/${encodeURIComponent(id)}/severity`, { method: "POST" }),
  
  
    event: (id) => request(`/api/events/${encodeURIComponent(id)}`),
  analysesForEvent: (eventId, limit = 50) =>
    request(`/api/analyses?event_id=${encodeURIComponent(eventId)}&limit=${encodeURIComponent(limit)}`),
  eventActions: (eventId, { status, priority } = {}) => {
    const query = new URLSearchParams({ limit: "200" });
    if (status) query.set("status", status);
    if (priority) query.set("priority", priority);
    return request(`/api/events/${encodeURIComponent(eventId)}/actions?${query}`);
  },
  actionPins: (eventId) => request(`/api/events/${encodeURIComponent(eventId)}/actions/geojson`),
  createAction: (eventId, body) =>
    request(`/api/events/${encodeURIComponent(eventId)}/actions`, { method: "POST", body }),
  updateAction: (id, changes) =>
    request(`/api/actions/${encodeURIComponent(id)}`, { method: "PATCH", body: changes }),
  deleteAction: (id) => request(`/api/actions/${encodeURIComponent(id)}`, { method: "DELETE" }),

};