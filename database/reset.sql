-- GeoFlood AI - DEVELOPMENT ONLY: deletes every GeoFlood table, function and all data.
DROP FUNCTION IF EXISTS compute_impact(BIGINT, TEXT, NUMERIC);
DROP FUNCTION IF EXISTS geo_area_km2(geometry);
DROP FUNCTION IF EXISTS geo_length_km(geometry);

DROP TABLE IF EXISTS
    emergency_actions, flood_reports, critical_infrastructure, agricultural_areas,
    affected_roads, affected_villages, reference_features, flood_zones, flood_analysis,
    satellite_images, disaster_events, satellite_sources, users
CASCADE;