-- =====================================================================
-- GeoFlood AI - database schema        PostgreSQL 12 + PostGIS 3.0
-- Apply:  psql "<DATABASE_URL>" -v ON_ERROR_STOP=1 -f database/schema.sql
-- Needs the postgis extension (created in Phase 13).
--
-- Conventions
--   * all geometry is EPSG:4326 (longitude/latitude). Measure area and length with
--     ::geography or by transforming to UTM, never in degrees.
--   * areas are km2, lengths km, distances m
--   * primary keys are BIGINT identity columns; timestamps are TIMESTAMPTZ
-- =====================================================================

-- ---------------------------------------------------------------- users
CREATE TABLE users (
    user_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username       VARCHAR(50)  NOT NULL UNIQUE,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  TEXT         NOT NULL,          -- a hash, never the password itself
    full_name      VARCHAR(100),
    role           VARCHAR(20)  NOT NULL DEFAULT 'analyst',
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT users_role_valid CHECK (role IN ('admin', 'analyst', 'viewer'))
);

-- ---------------------------------------------------------------- satellite_sources
CREATE TABLE satellite_sources (
    source_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         VARCHAR(100) NOT NULL UNIQUE,
    platform     VARCHAR(50)  NOT NULL,
    sensor_type  VARCHAR(10)  NOT NULL,
    provider     VARCHAR(100),
    description  TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT satellite_sources_sensor_valid CHECK (sensor_type IN ('SAR', 'optical'))
);

-- ---------------------------------------------------------------- disaster_events
CREATE TABLE disaster_events (
    event_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              VARCHAR(150) NOT NULL,
    region_name       VARCHAR(150),
    country           VARCHAR(100),
    status            VARCHAR(12)  NOT NULL DEFAULT 'monitoring',
    start_date        DATE,
    end_date          DATE,
    description       TEXT,
    area_of_interest  geometry(Polygon, 4326),
    created_by        BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT disaster_events_status_valid CHECK (status IN ('monitoring', 'active', 'resolved')),
    CONSTRAINT disaster_events_dates_valid
        CHECK (start_date IS NULL OR end_date IS NULL OR end_date >= start_date)
);
CREATE INDEX disaster_events_aoi_gix ON disaster_events USING GIST (area_of_interest);

-- ---------------------------------------------------------------- satellite_images
CREATE TABLE satellite_images (
    image_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id     BIGINT NOT NULL REFERENCES disaster_events (event_id) ON DELETE CASCADE,
    source_id    BIGINT NOT NULL REFERENCES satellite_sources (source_id) ON DELETE RESTRICT,
    uploaded_by  BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    image_role   VARCHAR(10) NOT NULL DEFAULT 'event',   -- 'baseline' = a before-flood image
    file_name    VARCHAR(255) NOT NULL,
    file_path    TEXT NOT NULL,
    file_sha256  CHAR(64),
    acquired_at  TIMESTAMPTZ,
    width_px     INTEGER,
    height_px    INTEGER,
    band_count   SMALLINT,
    crs          VARCHAR(50),
    footprint    geometry(Polygon, 4326) NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT satellite_images_role_valid CHECK (image_role IN ('event', 'baseline')),
    CONSTRAINT satellite_images_size_valid
        CHECK ((width_px IS NULL OR width_px > 0) AND (height_px IS NULL OR height_px > 0)),
    CONSTRAINT satellite_images_footprint_valid CHECK (ST_IsValid(footprint))
);
CREATE INDEX satellite_images_event_ix  ON satellite_images (event_id);
CREATE INDEX satellite_images_source_ix ON satellite_images (source_id);
CREATE INDEX satellite_images_footprint_gix ON satellite_images USING GIST (footprint);

-- ---------------------------------------------------------------- flood_analysis
-- One model run on one image. Column names follow the Python outputs of Phases 9 and 12.
-- baseline_image_id has no ON DELETE clause (= NO ACTION) so that deleting a whole event
-- (which cascades to both images and their analyses) still works.
CREATE TABLE flood_analysis (
    analysis_id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id                  BIGINT NOT NULL REFERENCES satellite_images (image_id) ON DELETE CASCADE,
    baseline_image_id         BIGINT REFERENCES satellite_images (image_id),
    baseline_method           VARCHAR(12) NOT NULL DEFAULT 'none',
    model_name                VARCHAR(100) NOT NULL,
    threshold                 NUMERIC(4,3) NOT NULL DEFAULT 0.500,
    status                    VARCHAR(10) NOT NULL DEFAULT 'completed',
    error_message             TEXT,
    valid_area_km2            NUMERIC(14,6),
    nodata_area_km2           NUMERIC(14,6),
    water_pixels              BIGINT,
    water_area_km2            NUMERIC(14,6),      -- all detected water
    water_pct_of_valid        NUMERIC(7,3),
    permanent_water_area_km2  NUMERIC(14,6),      -- NULL when there is no baseline
    new_flood_area_km2        NUMERIC(14,6),      -- NULL when there is no baseline
    new_flood_pct_of_valid    NUMERIC(7,3),
    mean_confidence           NUMERIC(5,4),
    area_method               VARCHAR(80),
    severity                  VARCHAR(10),        -- filled in Phase 25
    mask_path                 TEXT,
    probability_path          TEXT,
    warnings                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_by                BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT flood_analysis_baseline_valid
        CHECK (baseline_method IN ('none', 'jrc', 'before_image')),
    CONSTRAINT flood_analysis_before_needs_image
        CHECK (baseline_method <> 'before_image' OR baseline_image_id IS NOT NULL),
    CONSTRAINT flood_analysis_status_valid
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT flood_analysis_severity_valid
        CHECK (severity IS NULL OR severity IN ('low', 'moderate', 'high', 'severe')),
    CONSTRAINT flood_analysis_threshold_valid CHECK (threshold BETWEEN 0 AND 1),
    CONSTRAINT flood_analysis_confidence_valid
        CHECK (mean_confidence IS NULL OR mean_confidence BETWEEN 0 AND 1),
    CONSTRAINT flood_analysis_areas_valid
        CHECK (coalesce(valid_area_km2, 0) >= 0 AND coalesce(nodata_area_km2, 0) >= 0
           AND coalesce(water_area_km2, 0) >= 0 AND coalesce(permanent_water_area_km2, 0) >= 0
           AND coalesce(new_flood_area_km2, 0) >= 0),
    CONSTRAINT flood_analysis_completed_has_areas
        CHECK (status <> 'completed' OR (valid_area_km2 IS NOT NULL AND water_area_km2 IS NOT NULL)),
    -- no baseline <=> no new-flood figure
    CONSTRAINT flood_analysis_baseline_fields
        CHECK (status <> 'completed' OR ((baseline_method = 'none') = (new_flood_area_km2 IS NULL))),
    -- permanent + new = total water (up to rounding)
    CONSTRAINT flood_analysis_split_consistent
        CHECK (permanent_water_area_km2 IS NULL OR new_flood_area_km2 IS NULL OR water_area_km2 IS NULL
           OR abs(permanent_water_area_km2 + new_flood_area_km2 - water_area_km2) < 0.00001)
);
CREATE INDEX flood_analysis_image_ix ON flood_analysis (image_id);

-- ---------------------------------------------------------------- flood_zones
-- Classes are mutually exclusive: 'water' (no baseline available), or 'permanent_water' and
-- 'new_flood' (baseline available; together they make up the total water).
CREATE TABLE flood_zones (
    zone_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id      BIGINT NOT NULL REFERENCES flood_analysis (analysis_id) ON DELETE CASCADE,
    zone_type        VARCHAR(15) NOT NULL,
    poly_no          INTEGER NOT NULL,               -- poly_id from Phase 11 (1 = largest)
    n_pixels         BIGINT,
    area_km2         NUMERIC(14,6) NOT NULL,
    mean_confidence  NUMERIC(5,4),
    geom             geometry(MultiPolygon, 4326) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT flood_zones_unique UNIQUE (analysis_id, zone_type, poly_no),
    CONSTRAINT flood_zones_type_valid CHECK (zone_type IN ('water', 'permanent_water', 'new_flood')),
    CONSTRAINT flood_zones_area_valid CHECK (area_km2 >= 0),
    CONSTRAINT flood_zones_geom_valid CHECK (ST_IsValid(geom))
);
CREATE INDEX flood_zones_geom_gix ON flood_zones USING GIST (geom);

-- ---------------------------------------------------------------- reference_features
-- Real-world features (loaded from OpenStreetMap etc.) that flood zones are compared against.
CREATE TABLE reference_features (
    feature_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    layer       VARCHAR(20) NOT NULL,
    name        VARCHAR(200),
    category    VARCHAR(50),                         -- e.g. hospital, school, primary road
    source      VARCHAR(50) NOT NULL,
    source_ref  VARCHAR(50),                         -- e.g. the OpenStreetMap id
    properties  JSONB NOT NULL DEFAULT '{}'::jsonb,
    geom        geometry(Geometry, 4326) NOT NULL,
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT reference_features_source_unique UNIQUE (layer, source, source_ref),
    CONSTRAINT reference_features_layer_valid
        CHECK (layer IN ('village', 'road', 'farmland', 'infrastructure')),
    CONSTRAINT reference_features_geom_matches_layer CHECK (
        (layer = 'road'     AND GeometryType(geom) IN ('LINESTRING', 'MULTILINESTRING'))
     OR (layer = 'farmland' AND GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON'))
     OR (layer IN ('village', 'infrastructure')
                            AND GeometryType(geom) IN ('POINT', 'POLYGON', 'MULTIPOLYGON'))
    )
);
CREATE INDEX reference_features_layer_ix ON reference_features (layer);
CREATE INDEX reference_features_geom_gix ON reference_features USING GIST (geom);

-- ---------------------------------------------------------------- impact tables
-- zone_type says which flood class was compared: 'new_flood' when a baseline exists,
-- otherwise 'water'. Distances are in metres.
CREATE TABLE affected_villages (
    affected_village_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id          BIGINT NOT NULL REFERENCES flood_analysis (analysis_id) ON DELETE CASCADE,
    feature_id           BIGINT NOT NULL REFERENCES reference_features (feature_id) ON DELETE CASCADE,
    zone_type            VARCHAR(15) NOT NULL,
    relation             VARCHAR(10) NOT NULL,       -- 'inside' (touches the zone) or 'near'
    distance_m           NUMERIC(10,2) NOT NULL DEFAULT 0,
    flooded_area_km2     NUMERIC(14,6),              -- only when the village is a polygon
    flooded_pct          NUMERIC(6,3),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT affected_villages_unique UNIQUE (analysis_id, feature_id, zone_type),
    CONSTRAINT affected_villages_zone_valid CHECK (zone_type IN ('water', 'new_flood')),
    CONSTRAINT affected_villages_relation_valid CHECK (relation IN ('inside', 'near')),
    CONSTRAINT affected_villages_inside_distance CHECK (relation <> 'inside' OR distance_m = 0),
    CONSTRAINT affected_villages_pct_valid CHECK (flooded_pct IS NULL OR flooded_pct BETWEEN 0 AND 100)
);
CREATE INDEX affected_villages_feature_ix ON affected_villages (feature_id);

CREATE TABLE affected_roads (
    affected_road_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id        BIGINT NOT NULL REFERENCES flood_analysis (analysis_id) ON DELETE CASCADE,
    feature_id         BIGINT NOT NULL REFERENCES reference_features (feature_id) ON DELETE CASCADE,
    zone_type          VARCHAR(15) NOT NULL,
    flooded_length_km  NUMERIC(12,6) NOT NULL,
    flooded_pct        NUMERIC(6,3),                 -- share of the road's length that is flooded
    flooded_geom       geometry(MultiLineString, 4326) NOT NULL,   -- the flooded part only
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT affected_roads_unique UNIQUE (analysis_id, feature_id, zone_type),
    CONSTRAINT affected_roads_zone_valid CHECK (zone_type IN ('water', 'new_flood')),
    CONSTRAINT affected_roads_length_valid CHECK (flooded_length_km >= 0),
    CONSTRAINT affected_roads_pct_valid CHECK (flooded_pct IS NULL OR flooded_pct BETWEEN 0 AND 100)
);
CREATE INDEX affected_roads_feature_ix ON affected_roads (feature_id);
CREATE INDEX affected_roads_geom_gix ON affected_roads USING GIST (flooded_geom);

CREATE TABLE agricultural_areas (
    agricultural_area_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id           BIGINT NOT NULL REFERENCES flood_analysis (analysis_id) ON DELETE CASCADE,
    feature_id            BIGINT NOT NULL REFERENCES reference_features (feature_id) ON DELETE CASCADE,
    zone_type             VARCHAR(15) NOT NULL,
    flooded_area_km2      NUMERIC(14,6) NOT NULL,
    flooded_pct           NUMERIC(6,3),              -- share of the field that is flooded
    flooded_geom          geometry(MultiPolygon, 4326) NOT NULL,   -- the flooded part only
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT agricultural_areas_unique UNIQUE (analysis_id, feature_id, zone_type),
    CONSTRAINT agricultural_areas_zone_valid CHECK (zone_type IN ('water', 'new_flood')),
    CONSTRAINT agricultural_areas_area_valid CHECK (flooded_area_km2 >= 0),
    CONSTRAINT agricultural_areas_pct_valid CHECK (flooded_pct IS NULL OR flooded_pct BETWEEN 0 AND 100)
);
CREATE INDEX agricultural_areas_feature_ix ON agricultural_areas (feature_id);
CREATE INDEX agricultural_areas_geom_gix ON agricultural_areas USING GIST (flooded_geom);

CREATE TABLE critical_infrastructure (
    critical_infrastructure_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id                 BIGINT NOT NULL REFERENCES flood_analysis (analysis_id) ON DELETE CASCADE,
    feature_id                  BIGINT NOT NULL REFERENCES reference_features (feature_id) ON DELETE CASCADE,
    zone_type                   VARCHAR(15) NOT NULL,
    relation                    VARCHAR(10) NOT NULL,   -- 'inside' or 'near' (within the chosen distance)
    distance_m                  NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT critical_infrastructure_unique UNIQUE (analysis_id, feature_id, zone_type),
    CONSTRAINT critical_infrastructure_zone_valid CHECK (zone_type IN ('water', 'new_flood')),
    CONSTRAINT critical_infrastructure_relation_valid CHECK (relation IN ('inside', 'near')),
    CONSTRAINT critical_infrastructure_inside_distance CHECK (relation <> 'inside' OR distance_m = 0)
);
CREATE INDEX critical_infrastructure_feature_ix ON critical_infrastructure (feature_id);

-- ---------------------------------------------------------------- flood_reports
CREATE TABLE flood_reports (
    report_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id       BIGINT NOT NULL REFERENCES disaster_events (event_id) ON DELETE CASCADE,
    analysis_id    BIGINT REFERENCES flood_analysis (analysis_id) ON DELETE SET NULL,
    title          VARCHAR(200) NOT NULL,
    summary        TEXT,
    report_format  VARCHAR(10),
    file_path      TEXT,
    generated_by   BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX flood_reports_event_ix ON flood_reports (event_id);

-- ---------------------------------------------------------------- emergency_actions
CREATE TABLE emergency_actions (
    action_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id     BIGINT NOT NULL REFERENCES disaster_events (event_id) ON DELETE CASCADE,
    title        VARCHAR(200) NOT NULL,
    description  TEXT,
    action_type  VARCHAR(20) NOT NULL,
    priority     VARCHAR(10) NOT NULL DEFAULT 'medium',
    status       VARCHAR(12) NOT NULL DEFAULT 'planned',
    location     geometry(Point, 4326),
    assigned_to  BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    created_by   BIGINT REFERENCES users (user_id) ON DELETE SET NULL,
    due_at       TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),   -- the backend sets this on every update
    CONSTRAINT emergency_actions_type_valid CHECK (action_type IN
        ('evacuation', 'rescue', 'shelter', 'relief_distribution', 'road_closure', 'medical', 'other')),
    CONSTRAINT emergency_actions_priority_valid CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT emergency_actions_status_valid
        CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled'))
);
CREATE INDEX emergency_actions_event_ix  ON emergency_actions (event_id, status);
CREATE INDEX emergency_actions_location_gix ON emergency_actions USING GIST (location);
