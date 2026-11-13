export const EVENT = {
  event_id: 2, name: "Assam flood demo", region_name: "Brahmaputra valley", country: "India", status: "active",
  start_date: "2026-10-27", end_date: null, description: null, created_at: "2026-10-27T10:00:00Z",
};

export const EVENT_ANALYSES = [
  { analysis_id: 4, original_filename: "India_747992_S1Hand.tif", severity: "severe", bounds_wgs84: [92.8614, 26.0325, 92.9074, 26.0785] },
  { analysis_id: 2, original_filename: "India_828067_S1Hand.tif", severity: "moderate", bounds_wgs84: [93.7352, 26.5384, 93.7812, 26.5844] },
  { analysis_id: 1, original_filename: "India_591317_S1Hand.tif", severity: null, bounds_wgs84: [92.9074, 26.5844, 92.9534, 26.6304] },
];

const action = (id, overrides) => ({
  action_id: id, event_id: 2, title: `Action ${id}`, description: null, action_type: "other", priority: "medium",
  status: "planned", longitude: null, latitude: null, assigned_to: null, assigned_to_username: null, created_by: 1,
  due_at: null, created_at: "2026-11-10T10:00:00Z", updated_at: "2026-11-10T10:00:00Z", ...overrides,
});

export const ACTIONS = [
  action(12, { title: "Evacuate the school", action_type: "evacuation", priority: "critical", longitude: 93.7554, latitude: 26.5834, due_at: "2020-01-01T00:00:00Z" }),
  action(11, { title: "Close the NH129 bridge", action_type: "road_closure", priority: "high", status: "in_progress", longitude: 93.76, latitude: 26.58, assigned_to: 1, assigned_to_username: "admin" }),
  action(10, { title: "Distribute food packets", action_type: "relief_distribution", priority: "low", status: "completed", due_at: "2020-01-01T00:00:00Z" }),
];

const pinFeature = (a) => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: [a.longitude, a.latitude] },
  properties: { action_id: a.action_id, title: a.title, action_type: a.action_type, priority: a.priority, status: a.status },
});
export const PINS = { type: "FeatureCollection", features: ACTIONS.filter((a) => a.longitude !== null).map(pinFeature) };
