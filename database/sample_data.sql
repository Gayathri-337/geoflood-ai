-- =====================================================================
-- GeoFlood AI - FABRICATED sample data for testing. Not real results.
-- Load into the TEST database only (the test script does this for you).
-- Rows refer to each other by name, so it works with auto-generated ids.
-- =====================================================================

INSERT INTO users (username, email, password_hash, full_name, role) VALUES
  ('admin_demo',   'admin@example.com',   'PLACEHOLDER-NOT-A-REAL-HASH', 'Demo Admin',   'admin'),
  ('analyst_demo', 'analyst@example.com', 'PLACEHOLDER-NOT-A-REAL-HASH', 'Demo Analyst', 'analyst');

INSERT INTO satellite_sources (name, platform, sensor_type, provider, description) VALUES
  ('Sen1Floods11 hand-labeled chips', 'Sentinel-1', 'SAR', 'Cloud to Street (dataset), ESA (imagery)',
   'Dataset chips: VV and VH backscatter in dB, 512 x 512 pixels'),
  ('Sentinel-1 (Copernicus Data Space)', 'Sentinel-1', 'SAR', 'ESA / Copernicus',
   'Planned for Phase 28. Not integrated yet.');

INSERT INTO disaster_events (name, region_name, country, status, description, area_of_interest, created_by)
VALUES ('DEMO: flood test event', 'Demo area near 26.6N, 92.9E', 'India', 'monitoring',
        'Fabricated event for testing the database. Not a real event record.',
        ST_MakeEnvelope(92.90, 26.57, 92.97, 26.64, 4326),
        (SELECT user_id FROM users WHERE username = 'admin_demo'));

INSERT INTO satellite_images (event_id, source_id, uploaded_by, image_role, file_name, file_path,
                              width_px, height_px, band_count, crs, footprint)
VALUES ((SELECT event_id  FROM disaster_events    WHERE name = 'DEMO: flood test event'),
        (SELECT source_id FROM satellite_sources  WHERE name = 'Sen1Floods11 hand-labeled chips'),
        (SELECT user_id   FROM users              WHERE username = 'analyst_demo'),
        'event', 'India_591317_S1Hand.tif',
        'ai/data/raw/sen1floods11/S1Hand/India_591317_S1Hand.tif',
        512, 512, 2, 'EPSG:4326',
        ST_MakeEnvelope(92.90, 26.57, 92.97, 26.64, 4326));   -- fabricated box, not the real footprint

-- Totals are set to match the three fabricated zones below (new 1.380 + permanent 2.207 = 3.587 km2)
INSERT INTO flood_analysis (image_id, baseline_method, model_name, threshold, status,
                            valid_area_km2, nodata_area_km2, water_area_km2, water_pct_of_valid,
                            permanent_water_area_km2, new_flood_area_km2, new_flood_pct_of_valid,
                            mean_confidence, area_method, created_by)
VALUES ((SELECT image_id FROM satellite_images WHERE file_name = 'India_591317_S1Hand.tif'),
        'jrc', 'unet_flood_best.pth', 0.500, 'completed',
        23.000000, 0.000000, 3.587000, 15.596,
        2.207000, 1.380000, 6.000,
        0.9000, 'WGS84 ellipsoid, exact per pixel row',
        (SELECT user_id FROM users WHERE username = 'analyst_demo'));

-- Zone areas are measured by PostGIS from the geometry itself
INSERT INTO flood_zones (analysis_id, zone_type, poly_no, area_km2, mean_confidence, geom)
SELECT (SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1),
       z.zone_type, z.poly_no,
       round((ST_Area(z.geom::geography) / 1e6)::numeric, 6),
       0.9000, ST_Multi(z.geom)
FROM (VALUES
    ('new_flood',       1, ST_MakeEnvelope(92.920, 26.590, 92.930, 26.600, 4326)),   -- zone A
    ('new_flood',       2, ST_MakeEnvelope(92.940, 26.610, 92.945, 26.615, 4326)),   -- zone B
    ('permanent_water', 1, ST_MakeEnvelope(92.910, 26.620, 92.950, 26.625, 4326))    -- a river
) AS z(zone_type, poly_no, geom);

INSERT INTO reference_features (layer, name, category, source, source_ref, geom) VALUES
  -- villages: Alpha is inside A, Beta inside B, Gamma is dry, Delta is only in the river
  ('village', 'DEMO Village Alpha', 'village', 'fabricated-demo', 'v1', ST_SetSRID(ST_MakePoint(92.925, 26.595), 4326)),
  ('village', 'DEMO Village Beta',  'village', 'fabricated-demo', 'v2', ST_SetSRID(ST_MakePoint(92.9425, 26.6125), 4326)),
  ('village', 'DEMO Village Gamma', 'village', 'fabricated-demo', 'v3', ST_SetSRID(ST_MakePoint(92.935, 26.605), 4326)),
  ('village', 'DEMO Village Delta', 'village', 'fabricated-demo', 'v4', ST_SetSRID(ST_MakePoint(92.912, 26.622), 4326)),
  -- roads: R1 crosses A, R2 is far away, R3 crosses B
  ('road', 'DEMO Road R1', 'track', 'fabricated-demo', 'r1', ST_GeomFromText('LINESTRING(92.915 26.595, 92.935 26.595)', 4326)),
  ('road', 'DEMO Road R2', 'track', 'fabricated-demo', 'r2', ST_GeomFromText('LINESTRING(92.950 26.600, 92.960 26.600)', 4326)),
  ('road', 'DEMO Road R3', 'track', 'fabricated-demo', 'r3', ST_GeomFromText('LINESTRING(92.9425 26.605, 92.9425 26.620)', 4326)),
  -- farmland: F1 half in A, F2 entirely in B, F3 dry
  ('farmland', 'DEMO Field F1', 'farmland', 'fabricated-demo', 'f1', ST_MakeEnvelope(92.926, 26.592, 92.934, 26.598, 4326)),
  ('farmland', 'DEMO Field F2', 'farmland', 'fabricated-demo', 'f2', ST_MakeEnvelope(92.9405, 26.6105, 92.9445, 26.6145, 4326)),
  ('farmland', 'DEMO Field F3', 'farmland', 'fabricated-demo', 'f3', ST_MakeEnvelope(92.950, 26.590, 92.955, 26.595, 4326)),
  -- infrastructure: H1 inside A, S1 about 250 m from A, SH1 about 390 m from B, BR1 far away
  ('infrastructure', 'DEMO Hospital H1', 'hospital', 'fabricated-demo', 'i1', ST_SetSRID(ST_MakePoint(92.9275, 26.5985), 4326)),
  ('infrastructure', 'DEMO School S1',   'school',   'fabricated-demo', 'i2', ST_SetSRID(ST_MakePoint(92.9325, 26.595), 4326)),
  ('infrastructure', 'DEMO Shelter SH1', 'shelter',  'fabricated-demo', 'i3', ST_SetSRID(ST_MakePoint(92.9425, 26.6185), 4326)),
  ('infrastructure', 'DEMO Bridge BR1',  'bridge',   'fabricated-demo', 'i4', ST_SetSRID(ST_MakePoint(92.960, 26.580), 4326));

INSERT INTO flood_reports (event_id, analysis_id, title, summary, report_format, generated_by)
VALUES ((SELECT event_id FROM disaster_events WHERE name = 'DEMO: flood test event'),
        (SELECT analysis_id FROM flood_analysis ORDER BY analysis_id LIMIT 1),
        'DEMO assessment report', 'Fabricated placeholder. Real reports are generated in Phase 27.',
        'html', (SELECT user_id FROM users WHERE username = 'analyst_demo'));

INSERT INTO emergency_actions (event_id, title, description, action_type, priority, status,
                               location, assigned_to, created_by)
SELECT ev.event_id, v.title, 'Fabricated example action.', v.action_type, v.priority, v.status, v.location,
       (SELECT user_id FROM users WHERE username = 'analyst_demo'),
       (SELECT user_id FROM users WHERE username = 'admin_demo')
FROM (SELECT event_id FROM disaster_events ORDER BY event_id LIMIT 1) ev
CROSS JOIN (VALUES
    ('DEMO: open relief shelter at Village Gamma', 'shelter',      'high',   'planned',
        ST_SetSRID(ST_MakePoint(92.935, 26.605), 4326)),
    ('DEMO: close road R1 section',                'road_closure', 'medium', 'in_progress',
        ST_SetSRID(ST_MakePoint(92.925, 26.595), 4326))
) AS v(title, action_type, priority, status, location);
