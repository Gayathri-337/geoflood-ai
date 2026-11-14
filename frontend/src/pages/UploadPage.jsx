import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useAuth } from "../auth/authContext.js";
import {
  MAX_UPLOAD_MB,
  checkAcquiredDate,
  checkBaselineFile,
  checkImageFile,
  chipMismatch,
  todayString,
} from "../uploadRules.js";

const ANALYST_ROLES = new Set(["analyst", "admin"]);
const EMPTY_EVENT = { open: false, name: "", region: "", country: "", busy: false, error: "" };

const sizeText = (file) => `${file.name} (${(file.size / (1024 * 1024)).toFixed(1)} MB)`;

export default function UploadPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canUpload = ANALYST_ROLES.has(user?.role);

  const [lists, setLists] = useState({ status: "loading", events: [], sources: [], error: "" });
  const [reloadKey, setReloadKey] = useState(0);
  const [eventId, setEventId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [image, setImage] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [acquiredAt, setAcquiredAt] = useState("");
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [newEvent, setNewEvent] = useState(EMPTY_EVENT);

  useEffect(() => {
    if (!canUpload) return undefined;
    let cancelled = false;
    Promise.all([api.events(100), api.sources()])
      .then(([events, sources]) => {
        if (cancelled) return;
        setLists({ status: "ready", events, sources, error: "" });
        setEventId(events.length ? String(events[0].event_id) : "");
        setSourceId(sources.length ? String(sources[0].source_id) : "");
      })
      .catch((err) => {
        if (!cancelled) setLists({ status: "error", events: [], sources: [], error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [canUpload, reloadKey]);

  // seconds since the upload started
  useEffect(() => {
    if (!submitting) return undefined;
    setElapsed(0);
    const timer = setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => clearInterval(timer);
  }, [submitting]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const problem =
      checkImageFile(image) ||
      checkBaselineFile(baseline) ||
      checkAcquiredDate(acquiredAt) ||
      (!eventId ? "Choose an event, or create one first." : "") ||
      (!sourceId ? "Choose the imagery source." : "");
    if (problem) {
      setFormError(problem);
      return;
    }
    setFormError("");
    setSubmitting(true);
    try {
      const created = await api.createAnalysis({ file: image, baselineFile: baseline, eventId, sourceId, acquiredAt });
      navigate(`/analyses/${created.analysis_id}`);
    } catch (err) {
      setFormError(err.message);
      setSubmitting(false);
    }
  }

  async function handleCreateEvent(event) {
    event.preventDefault();
    const name = newEvent.name.trim();
    if (!name) {
      setNewEvent((previous) => ({ ...previous, error: "Give the event a name." }));
      return;
    }
    setNewEvent((previous) => ({ ...previous, busy: true, error: "" }));
    try {
      const created = await api.createEvent({
        name,
        region_name: newEvent.region.trim() || null,
        country: newEvent.country.trim() || null,
      });
      setLists((previous) => ({ ...previous, events: [created, ...previous.events] }));
      setEventId(String(created.event_id));
      setNewEvent(EMPTY_EVENT);
    } catch (err) {
      setNewEvent((previous) => ({ ...previous, busy: false, error: err.message }));
    }
  }

  if (!canUpload) {
    return (
      <div className="alert alert-warning" role="alert">
        Uploading and analysing images needs the analyst role.
      </div>
    );
  }
  if (lists.status === "loading") {
    return (
      <div className="text-center text-muted py-5" role="status">
        Loading…
      </div>
    );
  }
  if (lists.status === "error") {
    return (
      <div className="alert alert-danger d-flex justify-content-between align-items-center" role="alert">
        <span>{lists.error}</span>
        <button
          type="button"
          className="btn btn-sm btn-outline-danger"
          onClick={() => {
            setLists({ status: "loading", events: [], sources: [], error: "" });
            setReloadKey((key) => key + 1);
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="row justify-content-center">
      <div className="col-lg-7 col-xl-6">
        <h1 className="h4">New analysis</h1>
        <p className="text-muted small">
          Upload a Sentinel-1 radar image. The model detects surface water and stores the result for an event. A
          512 × 512 chip takes a few seconds on a CPU; larger images take longer.
        </p>

        {newEvent.open && (
          <form onSubmit={handleCreateEvent} noValidate className="card card-body mb-3">
            <h2 className="h6">New event</h2>
            <div className="mb-2">
              <label htmlFor="new-event-name" className="form-label small mb-1">
                Event name
              </label>
              <input
                id="new-event-name"
                className="form-control form-control-sm"
                maxLength={150}
                value={newEvent.name}
                onChange={(e) => setNewEvent((previous) => ({ ...previous, name: e.target.value }))}
              />
            </div>
            <div className="row g-2 mb-2">
              <div className="col">
                <label htmlFor="new-event-region" className="form-label small mb-1">
                  Region (optional)
                </label>
                <input
                  id="new-event-region"
                  className="form-control form-control-sm"
                  value={newEvent.region}
                  onChange={(e) => setNewEvent((previous) => ({ ...previous, region: e.target.value }))}
                />
              </div>
              <div className="col">
                <label htmlFor="new-event-country" className="form-label small mb-1">
                  Country (optional)
                </label>
                <input
                  id="new-event-country"
                  className="form-control form-control-sm"
                  value={newEvent.country}
                  onChange={(e) => setNewEvent((previous) => ({ ...previous, country: e.target.value }))}
                />
              </div>
            </div>
            {newEvent.error && (
              <div className="alert alert-danger py-2" role="alert">
                {newEvent.error}
              </div>
            )}
            <div className="d-flex gap-2">
              <button type="submit" className="btn btn-primary btn-sm" disabled={newEvent.busy}>
                Create event
              </button>
              <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setNewEvent(EMPTY_EVENT)}>
                Cancel
              </button>
            </div>
          </form>
        )}

        <form onSubmit={handleSubmit} noValidate className="card card-body">
          <div className="mb-3">
            <label htmlFor="event" className="form-label">
              Event
            </label>
            <div className="d-flex gap-2">
              <select id="event" className="form-select" value={eventId} onChange={(e) => setEventId(e.target.value)}>
                {lists.events.length === 0 && <option value="">No events yet</option>}
                {lists.events.map((item) => (
                  <option key={item.event_id} value={String(item.event_id)}>
                    {item.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-outline-secondary text-nowrap"
                onClick={() => setNewEvent((previous) => ({ ...previous, open: true }))}
              >
                Create a new event
              </button>
            </div>
          </div>

          <div className="mb-3">
            <label htmlFor="source" className="form-label">
              Imagery source
            </label>
            <select id="source" className="form-select" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              {lists.sources.map((item) => (
                <option key={item.source_id} value={String(item.source_id)}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-3">
            <label htmlFor="image" className="form-label">
              Sentinel-1 image (GeoTIFF with 2 bands, VV and VH, in dB)
            </label>
            <input
              id="image"
              type="file"
              className="form-control"
              accept=".tif,.tiff"
              onChange={(e) => setImage(e.target.files?.[0] ?? null)}
            />
            <div className="form-text">
              {image ? sizeText(image) : `A .tif or .tiff file, up to ${MAX_UPLOAD_MB} MB, with a coordinate system.`}
            </div>
          </div>

          <div className="mb-3">
            <label htmlFor="baseline" className="form-label">
              Baseline water layer (optional)
            </label>
            <input
              id="baseline"
              type="file"
              className="form-control"
              accept=".tif,.tiff"
              onChange={(e) => setBaseline(e.target.files?.[0] ?? null)}
            />
            <div className="form-text">
              {baseline
                ? sizeText(baseline)
                : "A 1-band GeoTIFF on exactly the same grid as the image, 1 = water (for a dataset chip: its JRCWaterHand file). Without it, permanent and new water are not separated."}
            </div>
          </div>

          <div className="mb-3">
            <label htmlFor="acquired-at" className="form-label">
              Date the satellite took the image (optional)
            </label>
            <input
              id="acquired-at"
              type="date"
              className="form-control"
              min="2000-01-01"
              max={todayString()}
              value={acquiredAt}
              onChange={(e) => setAcquiredAt(e.target.value)}
            />
            <div className="form-text">
              Needed to compare images of the same area over time. This is the date of the satellite pass, not
              today&apos;s date. Without it the analysis works as before but is left out of the comparison.
            </div>
          </div>

          {image && baseline && chipMismatch(image.name, baseline.name) && (
            <div className="alert alert-warning py-2" role="status">
              These file names look like different chips ({image.name} and {baseline.name}). The server refuses the
              pair if they do not cover exactly the same area.
            </div>
          )}
          {formError && (
            <div className="alert alert-danger py-2" role="alert">
              {formError}
            </div>
          )}
          {submitting && (
            <div className="mb-3">
              <div className="progress" role="progressbar" aria-label="Uploading and analysing">
                <div className="progress-bar progress-bar-striped progress-bar-animated w-100" />
              </div>
              <div className="text-muted small mt-1">
                Working for {elapsed} s. Keep this page open. Every upload creates a new analysis.
              </div>
            </div>
          )}

          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Uploading and analysing…" : "Upload and analyse"}
          </button>
        </form>
      </div>
    </div>
  );
}
