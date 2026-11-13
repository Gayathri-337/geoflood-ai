import { useState } from "react";
import {
  ACTION_TYPES, MAX_DESCRIPTION, MAX_TITLE, PRIORITIES, buildCreatePayload, emptyForm, validateActionForm,
} from "../actions.js";

/**
 * The form for a new action.
 * pin           : { longitude, latitude } chosen on the map, or null (the page owns it so the map can show it)
 * onSubmit      : async (body) => ...  Reject with an Error to show its message in the form.
 */
export default function ActionForm({ user, pin, picking, onPickingChange, onClearPin, onSubmit, onClose }) {
  const [fields, setFields] = useState(emptyForm());
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const change = (name) => (event) => {
    const value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    setFields((previous) => ({ ...previous, [name]: value }));
  };

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const problem = validateActionForm(fields);
    if (problem) {
      setError(problem);
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      await onSubmit(buildCreatePayload(fields, user?.user_id, pin));
      setFields(emptyForm());
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="card card-body mb-3">
      <h2 className="h6">New action</h2>

      <div className="mb-2">
        <label htmlFor="action-title" className="form-label small mb-1">
          Title
        </label>
        <input
          id="action-title"
          className="form-control form-control-sm"
          maxLength={MAX_TITLE}
          value={fields.title}
          onChange={change("title")}
        />
      </div>

      <div className="row g-2 mb-2">
        <div className="col">
          <label htmlFor="action-type" className="form-label small mb-1">
            Type
          </label>
          <select id="action-type" className="form-select form-select-sm" value={fields.action_type} onChange={change("action_type")}>
            {ACTION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
        <div className="col">
          <label htmlFor="action-priority" className="form-label small mb-1">
            Priority
          </label>
          <select id="action-priority" className="form-select form-select-sm" value={fields.priority} onChange={change("priority")}>
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mb-2">
        <label htmlFor="action-description" className="form-label small mb-1">
          Description (optional)
        </label>
        <textarea
          id="action-description"
          className="form-control form-control-sm"
          rows={2}
          maxLength={MAX_DESCRIPTION}
          value={fields.description}
          onChange={change("description")}
        />
      </div>

      <div className="mb-2">
        <label htmlFor="action-due" className="form-label small mb-1">
          Due (optional)
        </label>
        <input id="action-due" type="datetime-local" className="form-control form-control-sm" value={fields.due} onChange={change("due")} />
      </div>

      <div className="form-check mb-2">
        <input id="action-assign" type="checkbox" className="form-check-input" checked={fields.assignToMe} onChange={change("assignToMe")} />
        <label htmlFor="action-assign" className="form-check-label small">
          Assign to me
        </label>
      </div>

      <div className="mb-3">
        <div className="small mb-1">Map pin (optional)</div>
        <div className="small text-muted mb-1" data-testid="pin-text">
          {pin ? `Pin at ${pin.latitude}, ${pin.longitude}` : "No pin yet."}
        </div>
        <div className="d-flex gap-2">
          <button
            type="button"
            className={`btn btn-sm ${picking ? "btn-primary" : "btn-outline-primary"}`}
            aria-pressed={picking}
            onClick={() => onPickingChange(!picking)}
          >
            {picking ? "Stop picking" : "Pick on map"}
          </button>
          {pin && (
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClearPin}>
              Clear pin
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="alert alert-danger py-2" role="alert">
          {error}
        </div>
      )}

      <div className="d-flex gap-2">
        <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
          {submitting ? "Saving…" : "Save action"}
        </button>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onClose}>
          Close
        </button>
      </div>
    </form>
  );
}
