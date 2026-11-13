import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { formatDate } from "../format.js";

const STATUS_BADGE = { monitoring: "secondary", active: "danger", resolved: "success" };

export default function EventsPage() {
  const [state, setState] = useState({ status: "loading", events: [], error: "" });
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .events(100)
      .then((events) => {
        if (!cancelled) setState({ status: "ready", events, error: "" });
      })
      .catch((err) => {
        if (!cancelled) setState({ status: "error", events: [], error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  if (state.status === "error") {
    return (
      <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
        <span>{state.error}</span>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          onClick={() => {
            setState({ status: "loading", events: [], error: "" });
            setReloadKey((key) => key + 1);
          }}
        >
          Try again
        </button>
      </div>
    );
  }
  if (state.status === "loading") {
    return (
      <div className="text-center text-muted py-5" role="status">
        Loading…
      </div>
    );
  }

  return (
    <>
      <h1 className="h4 mb-3">Events</h1>
      {state.events.length === 0 ? (
        <p className="text-muted">No events yet. Create one when you upload an image (New analysis).</p>
      ) : (
        <div className="table-responsive">
          <table className="table table-sm table-hover align-middle">
            <thead>
              <tr>
                <th>Event</th>
                <th>Region</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {state.events.map((e) => (
                <tr key={e.event_id}>
                  <td>
                    <Link to={`/events/${e.event_id}`}>{e.name}</Link>
                  </td>
                  <td>{[e.region_name, e.country].filter(Boolean).join(", ") || "–"}</td>
                  <td>
                    <span className={`badge text-bg-${STATUS_BADGE[e.status] || "secondary"}`}>{e.status}</span>
                  </td>
                  <td>{formatDate(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
