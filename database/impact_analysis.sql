-- =====================================================================
-- GeoFlood AI - impact analysis functions     PostgreSQL 12 + PostGIS 3.0
-- Apply AFTER schema.sql:
--   psql "<DATABASE_URL>" -v ON_ERROR_STOP=1 -f database/impact_analysis.sql
-- Safe to re-run (CREATE OR REPLACE).
--
--   geo_area_km2(geometry)    area in km2 on the WGS84 spheroid (0 for NULL or empty)
--   geo_length_km(geometry)   length in km on the WGS84 spheroid (0 for NULL or empty)
--   compute_impact(analysis_id, zone_type DEFAULT NULL, near_m DEFAULT 500)
--       Fills affected_villages, affected_roads, agricultural_areas and critical_infrastructure.
--       zone_type NULL = automatic: 'new_flood' if the analysis has a baseline, else 'water'.
--       Returns one row per layer with the number of features found.
-- =====================================================================

CREATE OR REPLACE FUNCTION geo_area_km2(g geometry) RETURNS numeric
LANGUAGE sql AS $$
    SELECT CASE WHEN g IS NULL OR ST_IsEmpty(g) THEN 0::numeric
                ELSE (ST_Area(g::geography) / 1000000.0)::numeric END
$$;

CREATE OR REPLACE FUNCTION geo_length_km(g geometry) RETURNS numeric
LANGUAGE sql AS $$
    SELECT CASE WHEN g IS NULL OR ST_IsEmpty(g) THEN 0::numeric
                ELSE (ST_Length(g::geography) / 1000.0)::numeric END
$$;

CREATE OR REPLACE FUNCTION compute_impact(
    p_analysis_id BIGINT,
    p_zone_type   TEXT    DEFAULT NULL,
    p_near_m      NUMERIC DEFAULT 500
) RETURNS TABLE (layer_name TEXT, features_affected INTEGER)
LANGUAGE plpgsql AS $$
DECLARE
    v_zone  TEXT;
    v_flood geometry;      -- all zones of this analysis and class, merged into one geometry
    n       INTEGER;
BEGIN
    SELECT CASE WHEN p_zone_type IS NOT NULL      THEN p_zone_type
                WHEN fa.baseline_method = 'none'  THEN 'water'
                ELSE 'new_flood' END
      INTO v_zone
      FROM flood_analysis fa
     WHERE fa.analysis_id = p_analysis_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'analysis % does not exist', p_analysis_id;
    END IF;
    IF v_zone NOT IN ('water', 'new_flood') THEN
        RAISE EXCEPTION 'zone type must be water or new_flood, got %', v_zone;
    END IF;
    IF p_near_m IS NULL OR p_near_m < 0 THEN
        RAISE EXCEPTION 'the near distance must be zero or positive';
    END IF;

    -- start clean, so running this twice never duplicates rows
    DELETE FROM affected_villages        WHERE analysis_id = p_analysis_id AND zone_type = v_zone;
    DELETE FROM affected_roads           WHERE analysis_id = p_analysis_id AND zone_type = v_zone;
    DELETE FROM agricultural_areas       WHERE analysis_id = p_analysis_id AND zone_type = v_zone;
    DELETE FROM critical_infrastructure  WHERE analysis_id = p_analysis_id AND zone_type = v_zone;

    SELECT ST_UnaryUnion(ST_Collect(z.geom)) INTO v_flood
      FROM flood_zones z
     WHERE z.analysis_id = p_analysis_id AND z.zone_type = v_zone;

    IF v_flood IS NULL THEN          -- this analysis has no zones of this class
        RETURN QUERY SELECT * FROM (VALUES ('village'::text, 0), ('road'::text, 0),
                                           ('farmland'::text, 0), ('infrastructure'::text, 0)) AS t(a, b);
        RETURN;
    END IF;

    -- ---------------- villages: inside, or within p_near_m metres
    WITH y AS (
        SELECT f.feature_id, f.geom AS full_geom,
               ST_Intersects(f.geom, v_flood) AS is_inside,
               ST_Distance(f.geom::geography, v_flood::geography) AS dist
          FROM reference_features f
         WHERE f.layer = 'village'
           AND ST_DWithin(f.geom::geography, v_flood::geography, p_near_m)
    ), z AS (
        SELECT y.*,
               CASE WHEN y.is_inside AND GeometryType(y.full_geom) IN ('POLYGON', 'MULTIPOLYGON')
                    THEN geo_area_km2(ST_CollectionExtract(
                             ST_Intersection(ST_MakeValid(y.full_geom), v_flood), 3))
               END AS flooded_km2
          FROM y
    )
    INSERT INTO affected_villages (analysis_id, feature_id, zone_type, relation, distance_m,
                                   flooded_area_km2, flooded_pct)
    SELECT p_analysis_id, z.feature_id, v_zone,
           CASE WHEN z.is_inside THEN 'inside' ELSE 'near' END,
           CASE WHEN z.is_inside THEN 0 ELSE round(z.dist::numeric, 2) END,
           round(z.flooded_km2, 6),
           CASE WHEN z.flooded_km2 IS NOT NULL AND geo_area_km2(z.full_geom) > 0
                THEN LEAST(100, round(100 * z.flooded_km2 / geo_area_km2(z.full_geom), 3)) END
      FROM z;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT 'village'::text, n;

    -- ---------------- roads: only the flooded part is stored
    WITH x AS (
        SELECT f.feature_id, f.geom AS full_geom,
               ST_Multi(ST_CollectionExtract(ST_Intersection(f.geom, v_flood), 2)) AS piece
          FROM reference_features f
         WHERE f.layer = 'road' AND ST_Intersects(f.geom, v_flood)
    )
    INSERT INTO affected_roads (analysis_id, feature_id, zone_type, flooded_length_km,
                                flooded_pct, flooded_geom)
    SELECT p_analysis_id, x.feature_id, v_zone,
           round(geo_length_km(x.piece), 6),
           CASE WHEN geo_length_km(x.full_geom) > 0
                THEN LEAST(100, round(100 * geo_length_km(x.piece) / geo_length_km(x.full_geom), 3)) END,
           x.piece
      FROM x
     WHERE NOT ST_IsEmpty(x.piece);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT 'road'::text, n;

    -- ---------------- farmland: only the flooded part is stored
    WITH x AS (
        SELECT f.feature_id, f.geom AS full_geom,
               ST_Multi(ST_CollectionExtract(
                   ST_Intersection(ST_MakeValid(f.geom), v_flood), 3)) AS piece
          FROM reference_features f
         WHERE f.layer = 'farmland' AND ST_Intersects(f.geom, v_flood)
    )
    INSERT INTO agricultural_areas (analysis_id, feature_id, zone_type, flooded_area_km2,
                                    flooded_pct, flooded_geom)
    SELECT p_analysis_id, x.feature_id, v_zone,
           round(geo_area_km2(x.piece), 6),
           CASE WHEN geo_area_km2(x.full_geom) > 0
                THEN LEAST(100, round(100 * geo_area_km2(x.piece) / geo_area_km2(x.full_geom), 3)) END,
           x.piece
      FROM x
     WHERE NOT ST_IsEmpty(x.piece);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT 'farmland'::text, n;

    -- ---------------- critical infrastructure: inside, or within p_near_m metres
    INSERT INTO critical_infrastructure (analysis_id, feature_id, zone_type, relation, distance_m)
    SELECT p_analysis_id, y.feature_id, v_zone,
           CASE WHEN y.is_inside THEN 'inside' ELSE 'near' END,
           CASE WHEN y.is_inside THEN 0 ELSE round(y.dist::numeric, 2) END
      FROM (SELECT f.feature_id,
                   ST_Intersects(f.geom, v_flood) AS is_inside,
                   ST_Distance(f.geom::geography, v_flood::geography) AS dist
              FROM reference_features f
             WHERE f.layer = 'infrastructure'
               AND ST_DWithin(f.geom::geography, v_flood::geography, p_near_m)) y;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN QUERY SELECT 'infrastructure'::text, n;
END;
$$;
