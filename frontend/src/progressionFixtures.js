// SYNTHETIC data shaped like GET /api/events/{id}/progression. None of these numbers is a real result.
const point = (id, observed, area, pct) => ({
  analysis_id: id, original_filename: `synthetic_${id}.tif`, observed_at: observed, water_area_km2: area,
  water_pct_of_valid: pct, valid_area_km2: 25, baseline_method: "none", overlap_with_first: 1,
});

export const PROGRESSION = {
  event_id: 2,
  series: [
    {
      series_id: 1,
      area_bounds_wgs84: [93.4, 26.3, 93.46, 26.35],
      points: [
        point(1, "2026-10-01T00:00:00Z", 2.5, 10),
        point(2, "2026-10-07T00:00:00Z", 4.2, 16.8),
        point(3, "2026-10-13T00:00:00Z", 6.8, 27.2),
      ],
      changes: [
        { from_analysis_id: 1, to_analysis_id: 2, days: 6, delta_km2: 1.7, pct_change: 68.0, direction: "more" },
        { from_analysis_id: 2, to_analysis_id: 3, days: 6, delta_km2: 2.6, pct_change: 61.9, direction: "more" },
      ],
      summary: {
        points: 3, first_analysis_id: 1, last_analysis_id: 3, total_delta_km2: 4.3, total_pct_change: 172.0,
        peak_analysis_id: 3,
      },
      warnings: [],
    },
  ],
  unassigned: [
    {
      analysis_id: 5, original_filename: "undated.tif", observed_at: null, reason: "no_date",
      detail: "No observation date was entered for this image, so it cannot be placed in time.",
    },
  ],
  criteria: { min_overlap: 0.8 },
  note:
    "This compares detected surface water (rivers and lakes included) between images of the same area. A change is " +
    "not proof that the flood grew or shrank: rain, wet soil, wind on the water and differences between the images " +
    "also change what the model detects.",
};

export const EMPTY_PROGRESSION = { event_id: 2, series: [], unassigned: [], criteria: { min_overlap: 0.8 }, note: PROGRESSION.note };
