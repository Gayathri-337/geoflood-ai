import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PRIORITIES, PRIORITY_COLOR, normalizePin } from "../actions.js";
import { api } from "../api/client.js";
import { useAuth } from "../auth/authContext.js";
import ActionForm from "../components/ActionForm.jsx";
import ActionsPanel from "../components/ActionsPanel.jsx";
import { formatDate } from "../format.js";
import EventMap from "../map/EventMap.jsx";
import { eventBounds } from "../map/eventBounds.js";
import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";

const ANALYST_ROLES = new Set(["analyst", "admin"]);
const EVENT_BADGE = { monitoring: "secondary", active: "danger", resolved: "success" };

export default function EventPage() {
  const { eventId } = useParams();
  const { user } = useAuth();
  const idValid = /^[1-9]\d{0,17}$/.test(eventId || "");
  const canEdit = ANALYST_ROLES.has(user?.role);
  const canDelete = user?.role === "admin";

  const [data, setData] = useState({ status: "loading", event: null, analyses: [], actions: [], pins: null, error: "" });
  const [filters, setFilters] = useState({ status: "", priority: "" });
  const [reloadKey, setReloadKey] = useState(0);
  const [mapVersion, setMapVersion] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [picking, setPicking] = useState(false);
  const [pin, setPin] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [panelError, setPanelError] = useState("");

  useEffect(() => {
    if (!idValid) return undefined;
    let cancelled = false;
    Promise.all([
      api.event(eventId),
      api.analysesForEvent(eventId),
      api.eventActions(eventId, filters),
      api.actionPins(eventId),
    ])
      .then(([event, analyses, actions, pins]) => {
        if (cancelled) return;
        setData({ status: "ready", event, analyses, actions, pins, error: "" });
        setMapVersion((version) => version + 1);
      })
      .catch((err) => {
        if (cancelled) return;
        const message = err.status === 404 ? `Event ${eventId} was not found.` : err.message;
        setData((previous) => ({ ...previous, status: "error", error: message }));
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, idValid, filters, reloadKey]);

  // only used when the map is first drawn
  const bounds = useMemo(() => eventBounds(data.analyses, data.pins), [data.analyses, data.pins]);

  const reload = () => setReloadKey((key) => key + 1);

  async function handleCreate(payload) {
    await api.createAction(eventId, payload); // an error goes back to the form
    setPin(null);
    setPicking(false);
    reload();
  }

  async function handleStatus(action, status) {
    setBusyId(action.action_id);
    setPanelError("");
    try {
      await api.updateAction(action.action_id, { status });
      reload();
    } catch (err) {
      setPanelError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(action) {
    setBusyId(action.action_id);
    setPanelError("");
    try {
      await api.deleteAction(action.action_id);
      reload();
    } catch (err) {
      setPanelError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  function handlePick(longitude, latitude) {
    setPin(normalizePin(longitude, latitude));
    setPicking(false);
  }

  function closeForm() {
    setFormOpen(false);
    setPicking(false);
    setPin(null);
  }

  if (!idValid) {
    return (
      <div className="alert alert-warning" role="alert">
        &quot;{eventId}&quot; is not a valid event number. <Link to="/events">Back to the events</Link>
      </div>
    );
  }
  if (data.status === "error") {
    return (
      <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
        <span>{data.error}</span>
        <button type="button" className="btn btn-sm btn-outline-danger" onClick={reload}>
          Try again
        </button>
      </div>
    );
  }
  if (!data.event) {
    return (
      <div className="text-center text-muted py-5" role="status">
        Loading…
      </div>
    );
  }

  const { event, analyses, actions, pins } = data;
  const place = [event.region_name, event.country].filter(Boolean).join(", ");

  return (
    <>
      <nav className="mb-2">
        <Link to="/events">← Events</Link>
      </nav>
      <h1 className="h4 mb-1">{event.name}</h1>
      <p className="text-muted small">
        {place && <span>{place} · </span>}
        <span className={`badge text-bg-${EVENT_BADGE[event.status] || "secondary"}`}>{event.status}</span>
        {event.start_date && <span> · started {event.start_date}</span>}
      </p>

      <div className="row g-3">
        <div className="col-lg-7">
          <div className="border rounded" style={{ height: "60vh", minHeight: 380 }}>
            <EventMap
              key={eventId}
              bounds={bounds}
              pins={pins}
              picking={picking}
              picked={pin}
              onPick={handlePick}
              version={mapVersion}
            />
          </div>
          <div className="text-muted small mt-1">
            {picking ? "Click the map to place the pin." : "Pins show where actions are needed."} Base map ©
            OpenStreetMap contributors.
          </div>
          <div className="small mt-1 d-flex gap-3 flex-wrap">
            {PRIORITIES.map((p) => (
              <span key={p.value}>
                <span
                  className="d-inline-block rounded-circle me-1"
                  style={{ width: 12, height: 12, background: PRIORITY_COLOR[p.value], verticalAlign: "-1px" }}
                />
                {p.label}
              </span>
            ))}
          </div>

          <div className="card mt-3">
            <div className="card-body">
              <h2 className="h6">Analyses of this event</h2>
              {analyses.length === 0 ? (
                <p className="small text-muted mb-0">
                  No analyses yet.{canEdit && <> <Link to="/upload">Upload one</Link>.</>}
                </p>
              ) : (
                <ul className="list-unstyled small mb-0">
                  {analyses.map((a) => (
                    <li key={a.analysis_id} className="d-flex justify-content-between">
                      <Link to={`/analyses/${a.analysis_id}`}>
                        Analysis {a.analysis_id}: {a.original_filename}
                      </Link>
                      {a.severity && (
                        <span className={`badge text-bg-${LEVEL_BADGE[a.severity] || "secondary"}`}>
                          {LEVEL_LABEL[a.severity] || a.severity}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-5">
          {canEdit &&
            (formOpen ? (
              <ActionForm
                user={user}
                pin={pin}
                picking={picking}
                onPickingChange={setPicking}
                onClearPin={() => setPin(null)}
                onSubmit={handleCreate}
                onClose={closeForm}
              />
            ) : (
              <button type="button" className="btn btn-primary btn-sm mb-3" onClick={() => setFormOpen(true)}>
                Add action
              </button>
            ))}
          <ActionsPanel
            actions={actions}
            filters={filters}
            onFilterChange={setFilters}
            canEdit={canEdit}
            canDelete={canDelete}
            busyId={busyId}
            onStatus={handleStatus}
            onDelete={handleDelete}
            error={panelError}
          />
          <p className="text-muted small mt-2">
            Last updated {formatDate(new Date().toISOString())}. Actions are a coordination aid for this project, not
            an official emergency system.
          </p>
        </div>
      </div>
    </>
  );
}
