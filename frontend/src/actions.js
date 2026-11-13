/** Words, colours and rules for emergency actions. Pure functions, no React. */

export const ACTION_TYPES = [
  { value: "evacuation", label: "Evacuation" },
  { value: "rescue", label: "Rescue" },
  { value: "shelter", label: "Shelter" },
  { value: "relief_distribution", label: "Relief distribution" },
  { value: "road_closure", label: "Road closure" },
  { value: "medical", label: "Medical" },
  { value: "other", label: "Other" },
];
export const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];
export const STATUSES = [
  { value: "planned", label: "Planned" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

const labels = (list) => Object.fromEntries(list.map((item) => [item.value, item.label]));
export const TYPE_LABEL = labels(ACTION_TYPES);
export const PRIORITY_LABEL = labels(PRIORITIES);
export const STATUS_LABEL = labels(STATUSES);

export const PRIORITY_COLOR = { low: "#6c757d", medium: "#0d6efd", high: "#fd7e14", critical: "#dc3545" };
export const PRIORITY_BADGE = { low: "secondary", medium: "primary", high: "warning", critical: "danger" };
export const STATUS_BADGE = { planned: "secondary", in_progress: "info", completed: "success", cancelled: "dark" };

export const CLOSED = new Set(["completed", "cancelled"]);
export const MAX_TITLE = 200;
export const MAX_DESCRIPTION = 5000;

/** The status changes offered for an action in the given status. Any change is allowed by the server. */
export function nextStatuses(status) {
  switch (status) {
    case "planned":
      return [
        { status: "in_progress", label: "Start" },
        { status: "completed", label: "Complete" },
        { status: "cancelled", label: "Cancel action" },
      ];
    case "in_progress":
      return [
        { status: "completed", label: "Complete" },
        { status: "cancelled", label: "Cancel action" },
      ];
    case "completed":
    case "cancelled":
      return [{ status: "planned", label: "Reopen" }];
    default:
      return [];
  }
}

/** True for an open action whose due time has passed. */
export function isOverdue(action, now = new Date()) {
  if (!action || !action.due_at || CLOSED.has(action.status)) return false;
  const due = new Date(action.due_at);
  return !Number.isNaN(due.getTime()) && due < now;
}

export function emptyForm() {
  return { title: "", action_type: "evacuation", priority: "medium", description: "", due: "", assignToMe: false };
}

/** An error message for the new-action form, or "" when it looks fine. The server checks everything again. */
export function validateActionForm(form) {
  const title = (form.title || "").trim();
  if (!title) return "Give the action a title.";
  if (title.length > MAX_TITLE) return `The title can have at most ${MAX_TITLE} characters.`;
  if (!ACTION_TYPES.some((t) => t.value === form.action_type)) return "Choose the type of action.";
  if (!PRIORITIES.some((p) => p.value === form.priority)) return "Choose a priority.";
  if ((form.description || "").length > MAX_DESCRIPTION) {
    return `The description can have at most ${MAX_DESCRIPTION} characters.`;
  }
  if (form.due && Number.isNaN(new Date(form.due).getTime())) return "The due time is not a valid date and time.";
  return "";
}

/** The JSON body for POST /api/events/{id}/actions. `form.due` is a datetime-local value (local time). */
export function buildCreatePayload(form, userId, location = null) {
  return {
    title: form.title.trim(),
    action_type: form.action_type,
    priority: form.priority,
    description: (form.description || "").trim() || null,
    location: location ? { longitude: location.longitude, latitude: location.latitude } : null,
    assigned_to: form.assignToMe && userId ? userId : null,
    due_at: form.due ? new Date(form.due).toISOString() : null,
  };
}

/** A clicked map position as a pin: longitude wrapped into -180..180, latitude limited to -90..90, 6 decimals. */
export function normalizePin(longitude, latitude) {
  const wrapped = ((((longitude + 180) % 360) + 360) % 360) - 180;
  const clamped = Math.max(-90, Math.min(90, latitude));
  const round = (value) => Math.round(value * 1e6) / 1e6;
  return { longitude: round(wrapped), latitude: round(clamped) };
}
