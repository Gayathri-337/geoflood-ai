
import { useState } from "react";
import {
  PRIORITIES, PRIORITY_BADGE, PRIORITY_LABEL, STATUSES, STATUS_BADGE, STATUS_LABEL, TYPE_LABEL, isOverdue, nextStatuses,
} from "../actions.js";
import { formatDate } from "../format.js";

/** The list of an event's actions with filters and, for those who may, status buttons and delete. */
export default function ActionsPanel({
  actions, filters, onFilterChange, canEdit, canDelete, busyId = null, onStatus, onDelete, error = "",
}) {
  const [confirmingId, setConfirmingId] = useState(null);

  return (
    <div className="card">
      <div className="card-body">
        <h2 className="h6">Emergency actions</h2>

        <div className="row g-2 mb-3">
          <div className="col">
            <label htmlFor="filter-status" className="form-label small mb-1">
              Filter by status
            </label>
            <select
              id="filter-status"
              className="form-select form-select-sm"
              value={filters.status}
              onChange={(e) => onFilterChange({ ...filters, status: e.target.value })}
            >
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="col">
            <label htmlFor="filter-priority" className="form-label small mb-1">
              Filter by priority
            </label>
            <select
              id="filter-priority"
              className="form-select form-select-sm"
              value={filters.priority}
              onChange={(e) => onFilterChange({ ...filters, priority: e.target.value })}
            >
              <option value="">All</option>
              {PRIORITIES.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && (
          <div className="alert alert-danger py-2" role="alert">
            {error}
          </div>
        )}

        {actions.length === 0 ? (
          <p className="text-muted small mb-0">No actions match.</p>
        ) : (
          <ul className="list-group list-group-flush">
            {actions.map((a) => (
              <li key={a.action_id} className="list-group-item px-0" data-testid={`action-${a.action_id}`}>
                <div className="d-flex justify-content-between align-items-start gap-2">
                  <strong>{a.title}</strong>
                  <span className="d-flex gap-1 flex-wrap justify-content-end">
                    <span className={`badge text-bg-${PRIORITY_BADGE[a.priority] || "secondary"}`}>
                      {PRIORITY_LABEL[a.priority] || a.priority}
                    </span>
                    <span className={`badge text-bg-${STATUS_BADGE[a.status] || "secondary"}`}>
                      {STATUS_LABEL[a.status] || a.status}
                    </span>
                  </span>
                </div>
                <div className="small text-muted">
                  {TYPE_LABEL[a.action_type] || a.action_type}
                  {a.assigned_to_username ? ` · assigned to ${a.assigned_to_username}` : ""}
                  {a.longitude !== null && a.longitude !== undefined ? " · has a map pin" : ""}
                </div>
                {a.due_at && (
                  <div className="small">
                    Due {formatDate(a.due_at)}
                    {isOverdue(a) && <span className="badge text-bg-danger ms-1">Overdue</span>}
                  </div>
                )}
                {a.description && <div className="small mt-1">{a.description}</div>}

                {canEdit && (
                  <div className="d-flex gap-2 flex-wrap mt-2">
                    {nextStatuses(a.status).map((next) => (
                      <button
                        key={next.status}
                        type="button"
                        className="btn btn-outline-secondary btn-sm"
                        disabled={busyId === a.action_id}
                        onClick={() => onStatus(a, next.status)}
                      >
                        {next.label}
                      </button>
                    ))}
                    {canDelete &&
                      (confirmingId === a.action_id ? (
                        <>
                          <button
                            type="button"
                            className="btn btn-danger btn-sm"
                            disabled={busyId === a.action_id}
                            onClick={() => {
                              setConfirmingId(null);
                              onDelete(a);
                            }}
                          >
                            Delete permanently
                          </button>
                          <button
                            type="button"
                            className="btn btn-outline-secondary btn-sm"
                            onClick={() => setConfirmingId(null)}
                          >
                            Keep
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="btn btn-outline-danger btn-sm"
                          onClick={() => setConfirmingId(a.action_id)}
                        >
                          Delete
                        </button>
                      ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
