-- =====================================================================
-- GeoFlood AI - spatial queries for one analysis
-- Needs impact_analysis.sql (for geo_area_km2 and geo_length_km).
--
-- Run:  psql "<DATABASE_URL>" -v aid=1 -v zone=new_flood -v near=500 \
--            -f database/spatial_queries.sql
--   aid   analysis_id
--   zone  'water' or 'new_flood'   (which flood class to compare against)
--   near  distance in metres for "near the flood" (infrastructure query)
--
-- Areas and lengths are on the spheroid. Q7 reads the stored impact tables, so run
-- SELECT * FROM compute_impact(:aid) first (the test script does).
-- =====================================================================

\echo
\echo '=== Q1. Flooded area per zone class (measured from the polygons) ==='
SELECT zone_type,
       count(*)                                                AS polygons,
       round((sum(ST_Area(geom::geography)) / 1e6)::numeric, 4) AS area_km2_measured,
       round(sum(area_km2), 4)                                 AS area_km2_stored
  FROM flood_zones
 WHERE analysis_id = :aid
 GROUP BY zone_type
 ORDER BY zone_type;

\echo
\echo '=== Q2. Analysis summary ==='
SELECT valid_area_km2, water_area_km2, permanent_water_area_km2, new_flood_area_km2,
       new_flood_pct_of_valid, baseline_method, severity
  FROM flood_analysis
 WHERE analysis_id = :aid;

\echo
\echo '=== Q3. Villages touching the flood zones ==='
SELECT f.name, GeometryType(f.geom) AS shape
  FROM reference_features f
 WHERE f.layer = 'village'
   AND EXISTS (SELECT 1 FROM flood_zones z
                WHERE z.analysis_id = :aid AND z.zone_type = :'zone'
                  AND ST_Intersects(f.geom, z.geom))
 ORDER BY f.name;

\echo
\echo '=== Q4. Roads crossing the flood zones: flooded length ==='
SELECT f.name,
       round(geo_length_km(f.geom), 3) AS road_km,
       round(geo_length_km(ST_CollectionExtract(ST_Intersection(f.geom, u.geom), 2)), 3) AS flooded_km
  FROM reference_features f
 CROSS JOIN (SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
               FROM flood_zones WHERE analysis_id = :aid AND zone_type = :'zone') u
 WHERE f.layer = 'road' AND ST_Intersects(f.geom, u.geom)
 ORDER BY flooded_km DESC, f.name;

\echo
\echo '=== Q5. Critical infrastructure inside, or within :near metres of, the flood ==='
SELECT f.name, f.category,
       CASE WHEN ST_Intersects(f.geom, u.geom) THEN 'inside' ELSE 'near' END AS relation,
       round(ST_Distance(f.geom::geography, u.geom::geography)::numeric, 1)  AS distance_m
  FROM reference_features f
 CROSS JOIN (SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
               FROM flood_zones WHERE analysis_id = :aid AND zone_type = :'zone') u
 WHERE f.layer = 'infrastructure'
   AND ST_DWithin(f.geom::geography, u.geom::geography, :near)
 ORDER BY distance_m, f.name;

\echo
\echo '=== Q6. Affected farmland: flooded area per field ==='
SELECT f.name,
       round(geo_area_km2(f.geom), 4) AS field_km2,
       round(geo_area_km2(ST_CollectionExtract(
                 ST_Intersection(ST_MakeValid(f.geom), u.geom), 3)), 4) AS flooded_km2
  FROM reference_features f
 CROSS JOIN (SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
               FROM flood_zones WHERE analysis_id = :aid AND zone_type = :'zone') u
 WHERE f.layer = 'farmland' AND ST_Intersects(f.geom, u.geom)
 ORDER BY flooded_km2 DESC, f.name;

\echo
\echo '=== Q7. Dashboard numbers from the stored impact tables ==='
SELECT 'villages affected' AS item, count(*)::numeric AS n, NULL::numeric AS total, ''::text AS unit
  FROM affected_villages WHERE analysis_id = :aid AND zone_type = :'zone'
UNION ALL
SELECT 'roads affected', count(*), round(coalesce(sum(flooded_length_km), 0), 3), 'km flooded'
  FROM affected_roads WHERE analysis_id = :aid AND zone_type = :'zone'
UNION ALL
SELECT 'farmland affected', count(*), round(coalesce(sum(flooded_area_km2), 0), 3), 'km2 flooded'
  FROM agricultural_areas WHERE analysis_id = :aid AND zone_type = :'zone'
UNION ALL
SELECT 'infrastructure affected', count(*), NULL, ''
  FROM critical_infrastructure WHERE analysis_id = :aid AND zone_type = :'zone';

\echo
\echo '=== Q8. Infrastructure by category and relation ==='
SELECT f.category, ci.relation, count(*) AS features
  FROM critical_infrastructure ci
  JOIN reference_features f ON f.feature_id = ci.feature_id
 WHERE ci.analysis_id = :aid AND ci.zone_type = :'zone'
 GROUP BY f.category, ci.relation
 ORDER BY f.category, ci.relation;
