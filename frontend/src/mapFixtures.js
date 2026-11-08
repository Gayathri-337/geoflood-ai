// Sample values for tests, NOT real results.
export const ANALYSIS = {
  analysis_id: 2,
  event_id: 2,
  image_id: 2,
  source_id: 1,
  original_filename: "India_828067_S1Hand.tif",
  status: "completed",
  created_at: "2026-11-03T17:02:44Z",
  model_name: "unet_flood_best.pth",
  threshold: 0.5,
  baseline_method: "jrc",
  height_px: 512,
  width_px: 512,
  crs: "EPSG:4326",
  bounds_wgs84: [93.735237, 26.538377, 93.781231, 26.584371],
  valid_area_km2: 23.35,
  nodata_area_km2: 0,
  water_pixels: 6000,
  water_area_km2: 0.54,
  water_pct_of_valid: 2.31,
  permanent_water_area_km2: 0.05,
  new_flood_area_km2: 0.49,
  new_flood_pct_of_valid: 2.1,
  new_flood_share_of_water_pct: 90.7,
  mean_confidence: 0.9,
  area_method: "WGS84 ellipsoid, exact per pixel row",
  severity: null,
  zone_count: 2,
  warnings: [],
  mask_url: "/api/analyses/2/mask",
  zones_url: "/api/analyses/2/zones",
};

const square = (west, south, size) => [
  [
    [west, south],
    [west + size, south],
    [west + size, south + size],
    [west, south + size],
    [west, south],
  ],
];

export const collection = (features) => ({ type: "FeatureCollection", features });

export const ZONES = collection([
  {
    type: "Feature",
    geometry: { type: "MultiPolygon", coordinates: [square(93.75, 26.55, 0.003)] },
    properties: { zone_id: 1, zone_type: "new_flood", poly_no: 1, n_pixels: 500, area_km2: 0.2, mean_confidence: 0.95 },
  },
  {
    type: "Feature",
    geometry: { type: "MultiPolygon", coordinates: [square(93.76, 26.56, 0.002)] },
    properties: { zone_id: 2, zone_type: "permanent_water", poly_no: 1, n_pixels: 100, area_km2: 0.05, mean_confidence: 0.9 },
  },
]);

// one bridge over the water (not counted as flooded) and one really flooded road
export const ROADS = collection([
  {
    type: "Feature",
    geometry: { type: "MultiLineString", coordinates: [[[93.755366, 26.583304], [93.754947, 26.583673]]] },
    properties: {
      feature_id: 9, name: null, category: "trunk", source_ref: "way/1",
      flooded_length_km: 0.058488, flooded_pct: 53.632, on_bridge: true,
    },
  },
  {
    type: "Feature",
    geometry: { type: "MultiLineString", coordinates: [[[93.77, 26.56], [93.771, 26.5605]]] },
    properties: {
      feature_id: 10, name: "Test Road", category: "residential", source_ref: "way/2",
      flooded_length_km: 0.12, flooded_pct: 80, on_bridge: false,
    },
  },
]);

const village = (id, name, relation, distance) => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: [93.76, 26.57 + id / 1000] },
  properties: {
    feature_id: id, name, category: "village", source_ref: `node/${id}`, relation, distance_m: distance,
    flooded_area_km2: null, flooded_pct: null,
  },
});

export const VILLAGES = collection([village(1, "Test Village", "near", 410.2)]);
export const VILLAGES_AFTER = collection([village(1, "Test Village", "near", 410.2), village(2, "Second Village", "inside", 0)]);
export const FARMLAND = collection([]);
export const INFRASTRUCTURE = collection([
  {
    type: "Feature",
    geometry: { type: "Point", coordinates: [93.77, 26.575] },
    properties: { feature_id: 20, name: "Test College", category: "college", source_ref: "node/20", relation: "near", distance_m: 260 },
  },
]);

export const SUMMARY = {
  analysis_id: 2,
  zone_type: "new_flood",
  compared_against: "new flood: water that is not on the baseline layer",
  baseline_method: "jrc",
  last_computed_at: "2026-11-03T17:06:12Z",
  villages: { count: 1, inside: 0, near: 1 },
  roads: { count: 1, flooded_length_km: 0.12, bridges: { count: 1, length_km: 0.058488 } },
  farmland: { count: 0, flooded_area_km2: 0 },
  infrastructure: { count: 1, inside: 0, near: 1, by_category: { college: { inside: 0, near: 1 } } },
  note: "Zero everywhere can mean either that impact has not been computed yet or that nothing was affected.",
};

export const SUMMARY_AFTER = { ...SUMMARY, villages: { count: 2, inside: 1, near: 1 } };